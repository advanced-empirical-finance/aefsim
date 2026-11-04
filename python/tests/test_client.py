"""The same nine scenarios as r/tests/testthat/test-client.R."""

import datetime as dt

import polars as pl
import pytest

import aefsim
from aefsim import client


class FakeResponse:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload

    def json(self):
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


def envelope(data, as_of="2027-02-09", set_id="P1-baseline"):
    return {"as_of": as_of, "parameter_set_id": set_id, "data": data}


CHECK_OK = {"ok": True, "fill_date": "2027-02-10", "parameter_set_id": "P1-baseline", "weights": {"AAPL": 0.3},
            "errors": [], "diagnostics": {"gross": 0.3, "net": 0.3, "cash": 0.7, "n_positions": 1, "max_abs_weight": 0.3}}
CHECK_BAD = {"ok": False, "submission_id": "team-01-x", "status": "rejected", "fill_date": "2027-02-10",
             "parameter_set_id": "P1-baseline", "weights": {"PENNY": 0.3},
             "errors": [{"code": "ineligible_ticker", "ticker": "PENNY", "message": "Fails the filter."}],
             "diagnostics": {"gross": 0.3, "net": 0.3, "cash": 0.7, "n_positions": 1, "max_abs_weight": 0.3}}


def test_the_universe_is_typed_and_carries_its_as_of(api):
    routes, calls = api
    routes["GET universe"] = (200, envelope([
        {"ticker": "AAPL", "name": "Apple", "exchange": "Nasdaq", "eligible": True, "sp500": True, "delisted_on": None},
        {"ticker": "PENNY", "name": "Penny", "exchange": "NYSE", "eligible": False, "sp500": False, "delisted_on": None},
    ]))
    u = aefsim.get_universe()
    assert isinstance(u, pl.DataFrame)
    assert u["ticker"].to_list() == ["AAPL", "PENNY"]
    assert u["eligible"].dtype == pl.Boolean
    assert u["delisted_on"].dtype == pl.Date
    assert u["as_of"].to_list() == [dt.date(2027, 2, 9)] * 2
    assert calls[0]["headers"]["Authorization"] == "Bearer aef_test"
    assert calls[0]["params"] is None


def test_the_calendar_and_the_rules_mark_what_comes_next(api):
    routes, _ = api
    routes["GET calendar"] = (200, envelope({"next_fill": "2027-02-10", "next_deadline": "2027-02-10T14:00:00Z", "fills": [
        {"date": "2027-02-09", "deadline": "2027-02-09T14:00:00Z"},
        {"date": "2027-02-10", "deadline": "2027-02-10T14:00:00Z"},
    ]}))
    routes["GET parameters"] = (200, envelope({"next_fill": "2027-02-10", "sets": [
        {"effective_from": "2027-02-08", "set_id": "P1-baseline", "cost_bps": 0},
        {"effective_from": "2027-03-01", "set_id": "P2-costs", "cost_bps": 10},
    ]}))
    cal = aefsim.get_calendar()
    assert cal["is_next"].to_list() == [False, True]
    assert cal.filter(pl.col("is_next"))["deadline"][0] == dt.datetime(2027, 2, 10, 14, tzinfo=dt.timezone.utc)
    p = aefsim.get_parameters()
    assert p["applies_next"].to_list() == [True, False]
    assert p["effective_from"].dtype == pl.Date


def test_validate_sends_as_of_and_weights_and_returns_a_check(api):
    routes, calls = api
    routes["POST validate"] = (200, envelope(CHECK_OK))
    x = aefsim.validate({"AAPL": 0.3}, as_of=dt.date(2027, 2, 9))
    assert calls[0]["json"]["as_of"] == "2027-02-09"
    assert calls[0]["json"]["weights"] == {"AAPL": 0.3}
    assert x.ok
    assert x.fill_date == dt.date(2027, 2, 10)
    assert "OK" in repr(x)


def test_weights_come_as_dicts_or_frames_bad_input_fails_early(api):
    routes, calls = api
    routes["POST validate"] = (200, envelope(CHECK_OK))
    aefsim.validate(pl.DataFrame({"ticker": ["AAPL", "MSFT"], "weight": [0.2, 0.1]}), as_of="2027-02-09")
    assert calls[-1]["json"]["weights"] == {"AAPL": 0.2, "MSFT": 0.1}

    class PandasSeriesLike:
        def to_dict(self):
            return {"AAPL": 0.25}

    aefsim.validate(PandasSeriesLike(), as_of="2027-02-09")
    assert calls[-1]["json"]["weights"] == {"AAPL": 0.25}
    aefsim.validate({}, as_of="2027-02-09")
    assert calls[-1]["json"]["weights"] == {}
    with pytest.raises(ValueError, match="finite"):
        aefsim.validate({"AAPL": float("nan")}, as_of="2027-02-09")
    with pytest.raises(ValueError, match="ticker names"):
        aefsim.validate({"": 0.2}, as_of="2027-02-09")
    with pytest.raises(ValueError, match="as_of"):
        aefsim.validate({"AAPL": 0.1}, as_of=None)


def test_a_rejected_submission_is_returned_with_a_warning_not_an_error(api):
    routes, calls = api
    routes["POST submit"] = (422, envelope(CHECK_BAD))
    with pytest.warns(UserWarning, match="ineligible_ticker"):
        x = aefsim.submit({"PENNY": 0.3}, as_of="2027-02-09", rationale="test")
    assert not x.ok
    assert x.status == "rejected"
    assert x.errors["ticker"].to_list() == ["PENNY"]
    assert calls[0]["json"]["rationale"] == "test"
    assert "ineligible_ticker PENNY" in repr(x)


def test_api_errors_carry_their_code_and_status_a_missing_token_fails_early(api, monkeypatch):
    routes, _ = api
    routes["GET portfolio"] = (401, {"error": {"code": "unauthorized", "message": "Send your team token."}})
    with pytest.raises(aefsim.AefsimError) as e:
        aefsim.get_portfolio()
    assert e.value.code == "unauthorized"
    assert e.value.status == 401
    monkeypatch.delenv("AEF_TOKEN")
    with pytest.raises(aefsim.AefsimError, match="No token"):
        aefsim.get_portfolio()


def test_lookups_retry_on_busy_servers_writes_never_do(api):
    routes, calls = api
    routes["GET leaderboard"] = (503, {"error": {"code": "not_ready", "message": "Later."}})
    routes["POST submit"] = (502, {"error": {"code": "bad_gateway", "message": "Down."}})
    with pytest.raises(aefsim.AefsimError):
        aefsim.get_leaderboard()
    assert len(calls) == 3
    calls.clear()
    with pytest.raises(aefsim.AefsimError):
        aefsim.submit({}, as_of="2027-02-09", rationale="x")
    assert len(calls) == 1


def test_submissions_keep_their_weights_per_row(api):
    routes, _ = api
    routes["GET submissions"] = (200, envelope([
        {"submission_id": "a", "submitted_at": "2027-02-09T13:00:00Z", "as_of": "2027-02-08", "fill_date": "2027-02-09",
         "status": "accepted", "error_code": None, "cancelled": False, "filled": True, "rationale": "x", "weights": {"AAPL": 0.5, "MSFT": 0.5}},
        {"submission_id": "b", "submitted_at": "2027-02-08T13:00:00Z", "as_of": "2027-02-05", "fill_date": "2027-02-08",
         "status": "accepted", "error_code": None, "cancelled": True, "filled": False, "rationale": "y", "weights": {}},
    ]))
    x = aefsim.get_submissions()
    assert x["weights"][0].to_list() == [{"ticker": "AAPL", "weight": 0.5}, {"ticker": "MSFT", "weight": 0.5}]
    assert x["weights"][1].to_list() == []
    assert x["submitted_at"][0] == dt.datetime(2027, 2, 9, 13, tzinfo=dt.timezone.utc)
    assert x["cancelled"].to_list() == [False, True]


def test_cancel_portfolio_performance_leaderboard_and_benchmarks_parse(api):
    routes, _ = api
    routes["DELETE submit/a"] = (200, envelope({"submission_id": "a", "cancelled_at": "2027-02-09T12:00:00Z", "fill_date": "2027-02-09"}))
    routes["GET portfolio"] = (200, envelope({"date": "2027-02-09", "nav": 1e6, "cash": 2e5, "positions": [
        {"ticker": "AAPL", "shares": 100.0, "price": 200.0, "value": 2e4, "weight": 0.02, "stale": False}]}))
    routes["GET performance"] = (200, envelope({"summary": [{"team_id": "team-01", "sharpe": 0.5}],
                                                "benchmarks": [{"pseudonym": "Market", "sharpe": 0.4}],
                                                "series": [{"date": "2027-02-09", "nav_net": 1e6}]}))
    routes["GET leaderboard"] = (200, envelope([{"pseudonym": "marmot", "you": True, "rank": 1, "sharpe": 0.5},
                                                {"pseudonym": "Market", "you": False, "rank": None, "sharpe": 0.4}]))
    routes["GET benchmarks"] = (200, envelope({"summary": [{"pseudonym": "Market", "sharpe": 0.4}],
                                               "series": [{"pseudonym": "Market", "team_id": "bot-market", "date": "2027-02-09", "nav_net": 1e6}]}))
    assert aefsim.cancel("a")["fill_date"] == dt.date(2027, 2, 9)
    p = aefsim.get_portfolio()
    assert p["date"] == dt.date(2027, 2, 9)
    assert p["positions"]["ticker"].to_list() == ["AAPL"]
    assert aefsim.get_performance()["series"]["date"][0] == dt.date(2027, 2, 9)
    lb = aefsim.get_leaderboard()
    assert lb["you"].to_list() == [True, False]
    assert lb["rank"].to_list() == [1, None]
    assert aefsim.get_benchmarks()["series"]["date"][0] == dt.date(2027, 2, 9)
