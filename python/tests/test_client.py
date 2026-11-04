"""The same eleven scenarios as r/tests/testthat/test-client.R, with the same messages word for word."""

import datetime as dt

import polars as pl
import pytest

import aefsim
from aefsim import client


class Raw:
    """A response body that is not JSON."""

    def __init__(self, text):
        self.text = text


class FakeResponse:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload

    def json(self):
        if isinstance(self._payload, Raw):
            raise ValueError("not JSON")
        return self._payload


@pytest.fixture
def api(monkeypatch):
    """Route requests to canned responses keyed by 'METHOD path'; record the calls."""
    monkeypatch.setenv("AEF_TOKEN", "aef_test")
    monkeypatch.setenv("AEF_URL", "https://example.org/aef")
    monkeypatch.setattr(client, "RETRY_WAIT", 0)
    routes, calls = {}, []

    def fake(method, url, headers=None, json=None, params=None, timeout=None):
        calls.append({"method": method, "url": url, "headers": headers, "json": json, "params": params})
        hit = routes.get(f"{method} {url.split('/aef/', 1)[1]}")
        if hit is None:
            hit = (404, {"error": {"code": "not_found", "message": "No such endpoint."}})
        return FakeResponse(*hit)

    monkeypatch.setattr(client.requests, "request", fake)
    return routes, calls


def envelope(data, close_date="2027-02-09", set_id="P1-baseline"):
    return {"close_date": close_date, "parameter_set_id": set_id, "data": data}


CHECK_OK = {"ok": True, "trade_date": "2027-02-10", "parameter_set_id": "P1-baseline", "weights": {"AAPL": 0.3},
            "errors": [], "diagnostics": {"gross": 0.3, "net": 0.3, "cash": 0.7, "n_positions": 1, "max_abs_weight": 0.3}}
CHECK_BAD = {"ok": False, "submission_id": "team-01-x", "status": "rejected", "trade_date": "2027-02-10",
             "parameter_set_id": "P1-baseline", "weights": {"PENNY": 0.3},
             "errors": [{"code": "ineligible_ticker", "ticker": "PENNY", "message": "Not eligible on 2027-02-09."}],
             "diagnostics": {"gross": 0.3, "net": 0.3, "cash": 0.7, "n_positions": 1, "max_abs_weight": 0.3}}


def message(e):
    return str(e.value)


def test_the_universe_is_typed_and_carries_its_close_date(api):
    routes, calls = api
    routes["GET universe"] = (200, envelope([
        {"ticker": "AAPL", "name": "Apple", "exchange": "Nasdaq", "sp500": True},
        {"ticker": "MSFT", "name": "Microsoft", "exchange": "Nasdaq", "sp500": True},
    ]))
    u = aefsim.get_universe()
    assert isinstance(u, pl.DataFrame)
    assert u["ticker"].to_list() == ["AAPL", "MSFT"]
    assert u["sp500"].dtype == pl.Boolean
    assert u["close_date"].to_list() == [dt.date(2027, 2, 9)] * 2
    assert calls[0]["headers"]["Authorization"] == "Bearer aef_test"
    assert calls[0]["params"] is None
    aefsim.get_universe(close_date=dt.date(2027, 2, 5))
    assert calls[-1]["params"] == {"close_date": "2027-02-05"}


def test_the_calendar_and_the_rules_mark_what_comes_next(api):
    routes, _ = api
    routes["GET calendar"] = (200, envelope({"next_trade_date": "2027-02-10", "next_deadline": "2027-02-10T14:00:00Z", "trading_days": [
        {"date": "2027-02-09", "deadline": "2027-02-09T14:00:00Z"},
        {"date": "2027-02-10", "deadline": "2027-02-10T14:00:00Z"},
    ]}))
    routes["GET parameters"] = (200, envelope({"next_trade_date": "2027-02-10", "sets": [
        {"effective_from": "2027-02-08", "set_id": "P1-baseline", "cost_bps": 0},
        {"effective_from": "2027-03-01", "set_id": "P2-costs", "cost_bps": 10},
    ]}))
    cal = aefsim.get_calendar()
    assert cal["is_next"].to_list() == [False, True]
    assert cal.filter(pl.col("is_next"))["deadline"][0] == dt.datetime(2027, 2, 10, 14, tzinfo=dt.timezone.utc)
    p = aefsim.get_parameters()
    assert p["applies_next"].to_list() == [True, False]
    assert p["effective_from"].dtype == pl.Date


def test_validate_sends_close_date_and_weights_and_returns_a_check(api):
    routes, calls = api
    routes["POST validate"] = (200, envelope(CHECK_OK))
    x = aefsim.validate(pl.DataFrame({"ticker": ["AAPL"], "weight": [0.3]}), close_date=dt.date(2027, 2, 9))
    assert calls[0]["json"]["close_date"] == "2027-02-09"
    assert calls[0]["json"]["weights"] == {"AAPL": 0.3}
    assert x.ok
    assert x.trade_date == dt.date(2027, 2, 10)
    assert x.weights.to_dicts() == [{"ticker": "AAPL", "weight": 0.3}]
    assert "Trades at the open on 2027-02-10 (rules P1-baseline)" in repr(x)


def test_weights_come_as_data_frames_or_dicts_bad_input_fails_early(api):
    routes, calls = api
    routes["POST validate"] = (200, envelope(CHECK_OK))
    aefsim.validate(pl.DataFrame({"ticker": ["AAPL", "MSFT"], "weight": [0.2, 0.1]}), close_date="2027-02-09")
    assert calls[-1]["json"]["weights"] == {"AAPL": 0.2, "MSFT": 0.1}
    aefsim.validate({"AAPL": 0.25}, close_date="2027-02-09")
    assert calls[-1]["json"]["weights"] == {"AAPL": 0.25}
    aefsim.validate(pl.DataFrame(schema={"ticker": pl.String, "weight": pl.Float64}), close_date="2027-02-09")
    assert calls[-1]["json"]["weights"] == {}
    example = 'pl.DataFrame({"ticker": ["AAPL"], "weight": [0.1]})'
    with pytest.raises(aefsim.AefsimError) as e:
        aefsim.validate(pl.DataFrame({"ticker": ["AAPL"], "weight": [None]}), close_date="2027-02-09")
    assert e.value.code == "malformed_weights"
    assert message(e) == "Each weight must be one finite number; check AAPL. [malformed_weights]"
    with pytest.raises(aefsim.AefsimError) as e:
        aefsim.validate({"": 0.2}, close_date="2027-02-09")
    assert message(e) == f"Every weight needs a ticker, such as {example}. [malformed_weights]"
    with pytest.raises(aefsim.AefsimError) as e:
        aefsim.validate(pl.DataFrame({"symbol": ["AAPL"], "w": [0.1]}), close_date="2027-02-09")
    assert message(e) == f"weights needs the columns ticker and weight, such as {example}. [malformed_weights]"
    with pytest.raises(aefsim.AefsimError) as e:
        aefsim.validate(pl.DataFrame({"ticker": ["AAPL", "aapl"], "weight": [0.1, 0.1]}), close_date="2027-02-09")
    assert message(e) == "Each ticker may appear only once in weights; check AAPL. [duplicate_ticker]"
    with pytest.raises(aefsim.AefsimError) as e:
        aefsim.validate({"AAPL": 0.1})
    assert message(e) == 'Give close_date: the date of the close your decision is based on, such as "2027-03-01". [invalid_close_date]'
    with pytest.raises(aefsim.AefsimError) as e:
        aefsim.validate({"AAPL": 0.1}, close_date="03/01/2027")
    assert message(e) == 'close_date must be a date in the form YYYY-MM-DD, such as "2027-03-01", not "03/01/2027". [invalid_close_date]'
    assert e.value.status is None
    assert len(calls) == 3


def test_a_rejected_submission_is_returned_with_a_warning_not_an_error(api):
    routes, calls = api
    routes["POST submit"] = (422, envelope(CHECK_BAD))
    with pytest.warns(UserWarning) as w:
        x = aefsim.submit({"PENNY": 0.3}, close_date="2027-02-09", rationale="test")
    assert str(w[0].message) == "Submission team-01-x was rejected and will not trade:\n  ineligible_ticker PENNY: Not eligible on 2027-02-09."
    assert not x.ok
    assert x.status == "rejected"
    assert x.errors["ticker"].to_list() == ["PENNY"]
    assert calls[0]["json"]["rationale"] == "test"
    assert "ineligible_ticker PENNY" in repr(x)


def test_api_errors_carry_their_code_and_status_a_missing_token_fails_early(api, monkeypatch, tmp_path):
    routes, _ = api
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(client, "_home", lambda: tmp_path)
    routes["GET portfolio"] = (401, {"error": {"code": "unknown_token", "message": "This server does not know your token."}})
    with pytest.raises(aefsim.AefsimError) as e:
        aefsim.get_portfolio()
    assert e.value.code == "unknown_token"
    assert e.value.status == 401
    assert message(e) == "This server does not know your token. (server: https://example.org/aef) [unknown_token]"
    monkeypatch.setenv("AEF_TOKEN", "")
    with pytest.raises(aefsim.AefsimError) as e:
        aefsim.get_portfolio()
    assert message(e) == "No team token. Run set_token() once to save it, or set the environment variable AEF_TOKEN. [missing_token]"
    monkeypatch.setenv("AEF_TOKEN", "aef_test")
    with pytest.raises(aefsim.AefsimError) as e:
        aefsim.cancel("")
    assert message(e) == "Give submission_id: the id submit() returned, or one from get_submissions(). [invalid_submission_id]"


def test_lookups_retry_on_busy_servers_writes_never_do(api):
    routes, calls = api
    routes["GET leaderboard"] = (503, {"error": {"code": "not_ready", "message": "Later."}})
    routes["POST submit"] = (502, Raw("<html>Bad gateway</html>"))
    with pytest.raises(aefsim.AefsimError) as e:
        aefsim.get_leaderboard()
    assert message(e) == "Later. [not_ready]"
    assert len(calls) == 3
    calls.clear()
    with pytest.raises(aefsim.AefsimError) as e:
        aefsim.submit({}, close_date="2027-02-09", rationale="x")
    assert message(e) == (
        "The simulation server at https://example.org/aef is not responding (HTTP 502). "
        "It may be restarting: try again in a few minutes, and tell the course team if it stays down. [server_unavailable]"
    )
    assert len(calls) == 1


def test_submissions_keep_their_weights_per_row(api):
    routes, _ = api
    routes["GET submissions"] = (200, envelope([
        {"submission_id": "a", "submitted_at": "2027-02-09T13:00:00Z", "close_date": "2027-02-08", "trade_date": "2027-02-09",
         "status": "accepted", "error_code": None, "cancelled": False, "traded": True, "rationale": "x", "weights": {"AAPL": 0.5, "MSFT": 0.5}},
        {"submission_id": "b", "submitted_at": "2027-02-08T13:00:00Z", "close_date": "2027-02-05", "trade_date": "2027-02-08",
         "status": "accepted", "error_code": None, "cancelled": True, "traded": False, "rationale": "y", "weights": {}},
    ]))
    x = aefsim.get_submissions()
    assert x["weights"][0].to_list() == [{"ticker": "AAPL", "weight": 0.5}, {"ticker": "MSFT", "weight": 0.5}]
    assert x["weights"][1].to_list() == []
    assert x["submitted_at"][0] == dt.datetime(2027, 2, 9, 13, tzinfo=dt.timezone.utc)
    assert x["trade_date"].to_list() == [dt.date(2027, 2, 9), dt.date(2027, 2, 8)]
    assert x["cancelled"].to_list() == [False, True]


def test_cancel_portfolio_performance_leaderboard_and_benchmarks_parse(api):
    routes, _ = api
    routes["DELETE submit/a"] = (200, envelope({"submission_id": "a", "cancelled_at": "2027-02-09T12:00:00Z", "trade_date": "2027-02-09"}))
    routes["GET portfolio"] = (200, envelope({"close_date": "2027-02-09", "portfolio_value": 1e6, "cash": 2e5, "positions": [
        {"ticker": "AAPL", "shares": 100, "price": 200.0, "value": 2e4, "weight": 0.02, "stale": False}]}))
    routes["GET performance"] = (200, envelope({"summary": [{"team_id": "team-01", "sharpe": 0.5}],
                                                "benchmarks": [{"pseudonym": "Market", "sharpe": 0.4}],
                                                "series": [{"date": "2027-02-09", "portfolio_value": 1e6}]}))
    routes["GET leaderboard"] = (200, envelope([{"pseudonym": "marmot", "you": True, "rank": 1, "sharpe": 0.5},
                                                {"pseudonym": "Market", "you": False, "rank": None, "sharpe": 0.4}]))
    routes["GET benchmarks"] = (200, envelope({"summary": [{"pseudonym": "Market", "sharpe": 0.4}],
                                               "series": [{"pseudonym": "Market", "team_id": "bot-market", "date": "2027-02-09", "portfolio_value": 1e6}]}))
    assert aefsim.cancel("a")["trade_date"] == dt.date(2027, 2, 9)
    p = aefsim.get_portfolio()
    assert p.height == 1
    assert p["close_date"][0] == dt.date(2027, 2, 9)
    assert p["portfolio_value"][0] == 1e6
    assert p.explode("positions").unnest("positions")["ticker"].to_list() == ["AAPL"]
    assert aefsim.get_performance()["series"]["portfolio_value"][0] == 1e6
    lb = aefsim.get_leaderboard()
    assert lb["you"].to_list() == [True, False]
    assert lb["rank"].to_list() == [1, None]
    assert aefsim.get_benchmarks()["series"]["date"][0] == dt.date(2027, 2, 9)


def test_an_unreachable_server_and_unexpected_answers_get_plain_messages(api, monkeypatch):
    routes, _ = api
    monkeypatch.setattr(client.requests, "request", client.requests.api.request)
    monkeypatch.setenv("AEF_URL", "http://127.0.0.1:9")
    with pytest.raises(aefsim.AefsimError) as e:
        aefsim.get_universe()
    assert message(e) == (
        "Could not reach the simulation server at http://127.0.0.1:9. Check your internet connection and try again; "
        "if it stays unreachable, tell the course team. [connection_failed]"
    )
    monkeypatch.undo()
    monkeypatch.setenv("AEF_TOKEN", "aef_test")
    monkeypatch.setenv("AEF_URL", "https://example.org/aef")
    monkeypatch.setattr(client.requests, "request", lambda *a, **k: FakeResponse(418, Raw("teapot")))
    with pytest.raises(aefsim.AefsimError) as e:
        aefsim.get_universe()
    assert message(e) == "Unexpected answer from the simulation server at https://example.org/aef (HTTP 418). [http_error]"
    assert e.value.status == 418


def test_set_token_asks_where_to_save_the_token_and_offers_to_add_it_to_gitignore(monkeypatch, tmp_path, capsys):
    project, home = tmp_path / "project", tmp_path / "home"
    project.mkdir()
    home.mkdir()
    monkeypatch.chdir(project)
    monkeypatch.delenv("AEF_TOKEN", raising=False)
    monkeypatch.setattr(client, "_is_interactive", lambda: True)
    monkeypatch.setattr(client, "_home", lambda: home)
    answers, prompts = [], []

    def fake_input(prompt):
        prompts.append(prompt)
        return answers.pop(0)

    monkeypatch.setattr("builtins.input", fake_input)
    answers[:] = [" aef_abc ", "project", "yes"]
    aefsim.set_token()
    assert client.os.environ["AEF_TOKEN"] == "aef_abc"
    assert (project / ".env").read_text() == "AEF_TOKEN=aef_abc\n"
    assert (project / ".gitignore").read_text() == ".env\n"
    assert prompts == [
        "Paste your team's token (it starts with aef_): ",
        "Where do you want to save it? Enter 'project' for .env in this project's folder or 'home' for your home folder: ",
        "Do you want to add .env to .gitignore, so your token never ends up in Git? It is highly recommended! Enter 'yes' or 'no': ",
    ]
    assert capsys.readouterr().out.splitlines() == [
        ".env added to .gitignore.", f"Your token is saved in {project / '.env'} and set for this session."]
    monkeypatch.delenv("AEF_TOKEN")
    assert client._token() == "aef_abc"

    (home / ".env").write_text("OTHER=1\nAEF_TOKEN=aef_old\n")
    prompts.clear()
    answers[:] = ["aef_new", "home", "yes"]
    aefsim.set_token()
    assert (home / ".env").read_text() == "OTHER=1\nAEF_TOKEN=aef_new\n"
    assert prompts[2] == ".env already holds a token. Do you want to replace it? Enter 'yes' or 'no': "
    capsys.readouterr()

    answers[:] = ["aef_session", "later"]
    aefsim.set_token()
    assert client.os.environ["AEF_TOKEN"] == "aef_session"
    assert capsys.readouterr().out.strip() == "Not saved: the token is set for this session only. Run set_token() again to save it."

    with pytest.raises(aefsim.AefsimError) as e:
        aefsim.set_token("nope")
    assert message(e) == "That is not a simulation token: team tokens start with aef_. [invalid_token]"
    monkeypatch.setattr(client, "_is_interactive", lambda: False)
    with pytest.raises(aefsim.AefsimError) as e:
        aefsim.set_token()
    assert message(e) == (
        "set_token() asks for your token, which needs an interactive session. "
        'In a script, use set_token("aef_...") or set the environment variable AEF_TOKEN. [missing_token]'
    )
    aefsim.set_token("aef_script")
    assert client.os.environ["AEF_TOKEN"] == "aef_script"
