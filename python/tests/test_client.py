import pandas as pd
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
    routes, calls = {}, []

    def fake(method, url, headers=None, json=None, params=None, timeout=None):
        calls.append({"method": method, "url": url, "headers": headers, "json": json, "params": params})
        path = url.split("/aef/", 1)[1]
        status, payload = routes.get(f"{method} {path}", (404, {"error": {"code": "not_found", "message": "No such endpoint."}}))
        return FakeResponse(status, payload)

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


def test_universe_is_a_typed_frame_with_as_of(api):
    routes, calls = api
    routes["GET universe"] = (200, envelope([
        {"ticker": "AAPL", "name": "Apple", "exchange": "Nasdaq", "eligible": True, "sp500": True, "delisted_on": None},
        {"ticker": "PENNY", "name": "Penny", "exchange": "NYSE", "eligible": False, "sp500": False, "delisted_on": None},
    ]))
    u = aefsim.get_universe()
    assert list(u["ticker"]) == ["AAPL", "PENNY"]
    assert u["eligible"].dtype == bool
    assert pd.api.types.is_datetime64_any_dtype(u["delisted_on"])
    assert u.attrs["as_of"] == pd.Timestamp("2027-02-09")
    assert calls[0]["headers"]["Authorization"] == "Bearer aef_test"
    assert calls[0]["params"] is None


def test_validate_sends_as_of_and_weights(api):
    routes, calls = api
    routes["POST validate"] = (200, envelope(CHECK_OK))
    x = aefsim.validate({"AAPL": 0.3}, as_of=pd.Timestamp("2027-02-09"))
    assert calls[0]["json"]["as_of"] == "2027-02-09"
    assert calls[0]["json"]["weights"] == {"AAPL": 0.3}
    assert x.ok and x.fill_date == pd.Timestamp("2027-02-10")
    assert "OK" in repr(x)


def test_weights_from_series_and_frames_and_bad_input(api):
    routes, calls = api
    routes["POST validate"] = (200, envelope(CHECK_OK))
    aefsim.validate(pd.DataFrame({"ticker": ["AAPL", "MSFT"], "weight": [0.2, 0.1]}), as_of="2027-02-09")
    assert calls[-1]["json"]["weights"] == {"AAPL": 0.2, "MSFT": 0.1}
    aefsim.validate(pd.Series({"AAPL": 0.25}), as_of="2027-02-09")
    assert calls[-1]["json"]["weights"] == {"AAPL": 0.25}
    class PolarsLike:
        columns = ["ticker", "weight"]

        def to_dicts(self):
            return [{"ticker": "KO", "weight": 0.1}]

    aefsim.validate(PolarsLike(), as_of="2027-02-09")
    assert calls[-1]["json"]["weights"] == {"KO": 0.1}
    aefsim.validate({}, as_of="2027-02-09")
    assert calls[-1]["json"]["weights"] == {}
    with pytest.raises(ValueError, match="finite"):
        aefsim.validate({"AAPL": float("nan")}, as_of="2027-02-09")
    with pytest.raises(ValueError, match="as_of"):
        aefsim.validate({"AAPL": 0.1}, as_of=None)


def test_rejected_submission_warns_and_returns(api):
    routes, calls = api
    routes["POST submit"] = (422, envelope(CHECK_BAD))
    with pytest.warns(UserWarning, match="ineligible_ticker"):
        x = aefsim.submit({"PENNY": 0.3}, as_of="2027-02-09", rationale="test")
    assert not x.ok and x.status == "rejected"
    assert list(x.errors["ticker"]) == ["PENNY"]
    assert calls[0]["json"]["rationale"] == "test"
    assert "ineligible_ticker PENNY" in repr(x)


def test_api_errors_raise_with_code(api, monkeypatch):
    routes, _ = api
    routes["GET portfolio"] = (401, {"error": {"code": "unauthorized", "message": "Send your team token."}})
    with pytest.raises(aefsim.AefsimError) as e:
        aefsim.get_portfolio()
    assert e.value.code == "unauthorized" and e.value.status == 401
    monkeypatch.delenv("AEF_TOKEN")
    with pytest.raises(aefsim.AefsimError, match="No token"):
        aefsim.get_portfolio()


def test_get_requests_retry_but_writes_do_not(api, monkeypatch):
    routes, calls = api
    monkeypatch.setattr(client.time, "sleep", lambda s: None)
    routes["GET leaderboard"] = (503, {"error": {"code": "not_ready", "message": "later"}})
    routes["POST submit"] = (502, None)
    with pytest.raises(aefsim.AefsimError):
        aefsim.get_leaderboard()
    assert len(calls) == 3
    with pytest.raises(aefsim.AefsimError):
        aefsim.submit({}, as_of="2027-02-09", rationale="x")
    assert len(calls) == 4


def test_submissions_portfolio_performance_cancel(api):
    routes, _ = api
    routes["GET submissions"] = (200, envelope([
        {"submission_id": "a", "submitted_at": "2027-02-09T13:00:00Z", "as_of": "2027-02-08", "fill_date": "2027-02-09",
         "status": "accepted", "error_code": None, "cancelled": False, "filled": True, "rationale": "x", "weights": {"AAPL": 0.5}},
        {"submission_id": "b", "submitted_at": "2027-02-08T13:00:00Z", "as_of": "2027-02-05", "fill_date": "2027-02-08",
         "status": "accepted", "error_code": None, "cancelled": True, "filled": False, "rationale": "y", "weights": {}},
    ]))
    routes["GET portfolio"] = (200, envelope({"date": "2027-02-09", "nav": 1e6, "cash": 2e5, "positions": [
        {"ticker": "AAPL", "shares": 100.0, "price": 200.0, "value": 2e4, "weight": 0.02, "stale": False}]}))
    routes["GET performance"] = (200, envelope({"summary": [{"team_id": "team-01", "sharpe": 0.5}],
                                                "benchmarks": [{"pseudonym": "Market", "sharpe": 0.4}],
                                                "series": [{"date": "2027-02-09", "nav_net": 1e6}]}))
    routes["DELETE submit/a"] = (200, envelope({"submission_id": "a", "cancelled_at": "2027-02-09T12:00:00Z", "fill_date": "2027-02-09"}))
    s = aefsim.get_submissions()
    assert s["weights"][0] == {"AAPL": 0.5} and s["weights"][1] == {}
    assert s["submitted_at"][0] == pd.Timestamp("2027-02-09 13:00", tz="UTC")
    assert list(aefsim.get_portfolio()["positions"]["ticker"]) == ["AAPL"]
    assert aefsim.get_performance()["series"]["date"][0] == pd.Timestamp("2027-02-09")
    assert aefsim.cancel("a")["fill_date"] == pd.Timestamp("2027-02-09")
