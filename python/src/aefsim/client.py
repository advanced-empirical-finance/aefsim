"""Functions mirroring the R package aefsim: same names, same columns."""

from __future__ import annotations

import datetime as dt
import math
import os
import time
import warnings
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

import polars as pl
import requests

VERSION = "0.1.0"
DEFAULT_URL = "https://eumel.tail81c88a.ts.net/aef"
RETRY_WAIT = 1.0  # seconds before the first retry of a GET; doubles each time
DATE_COLS = {"date", "as_of", "fill_date", "effective_from", "delisted_on", "start", "end", "next_fill"}
TIME_COLS = {"submitted_at", "deadline", "cancelled_at", "next_deadline", "time"}
WEIGHTS = pl.List(pl.Struct({"ticker": pl.String, "weight": pl.Float64}))


class AefsimError(Exception):
    """An error returned by the simulation API, with its ``code`` and HTTP ``status``."""

    def __init__(self, code: str, message: str, status: Optional[int] = None):
        super().__init__(f"{message} [{code}]")
        self.code = code
        self.message = message
        self.status = status


def set_token(token: str) -> None:
    """Use ``token`` for this session. Better: set the environment variable AEF_TOKEN."""
    if not isinstance(token, str) or not token:
        raise ValueError("token must be a non-empty string")
    os.environ["AEF_TOKEN"] = token


def set_url(url: str) -> None:
    """Point the client at another server, for example a test one."""
    os.environ["AEF_URL"] = url.rstrip("/")


def _call(method: str, path: str, body: Any = None, params: Optional[dict] = None, ok=(200,)):
    """One API call. GETs are retried on rate limits and gateway errors; writes are
    not, so a submission is never sent twice."""
    token = os.environ.get("AEF_TOKEN", "")
    if not token:
        raise AefsimError("no_token", "No token: call set_token() or set AEF_TOKEN.")
    url = os.environ.get("AEF_URL", DEFAULT_URL).rstrip("/") + "/" + path
    headers = {"Authorization": f"Bearer {token}", "User-Agent": f"aefsim Python client {VERSION}"}
    params = {k: v for k, v in (params or {}).items() if v is not None} or None
    tries = 3 if method == "GET" else 1
    for attempt in range(tries):
        resp = requests.request(method, url, headers=headers, json=body, params=params, timeout=60)
        if method == "GET" and resp.status_code in (429, 502, 503, 504) and attempt < tries - 1:
            time.sleep(RETRY_WAIT * 2 ** attempt)
            continue
        break
    try:
        payload = resp.json()
    except ValueError:
        payload = None
    if resp.status_code not in ok:
        err = (payload or {}).get("error") or {}
        raise AefsimError(err.get("code", "http_error"), err.get("message", f"HTTP status {resp.status_code}"), resp.status_code)
    return payload


def _frame(records, schema: Optional[dict] = None) -> pl.DataFrame:
    """JSON records to a polars DataFrame with typed date and time columns."""
    if records:
        df = pl.DataFrame(records, infer_schema_length=None, schema_overrides=schema)
    else:
        df = pl.DataFrame(schema=schema)
    for col in df.columns:
        if col in DATE_COLS:
            df = df.with_columns(_typed(df[col], pl.Date))
        elif col in TIME_COLS:
            df = df.with_columns(_typed(df[col], pl.Datetime("us", "UTC")))
    return df


def _typed(s: pl.Series, dtype) -> pl.Series:
    if s.dtype == pl.String:
        if dtype == pl.Date:
            return s.str.to_date("%Y-%m-%d", strict=False)
        return s.str.to_datetime("%Y-%m-%dT%H:%M:%SZ", time_zone="UTC", strict=False)
    return s.cast(dtype)


def _date(x) -> Optional[dt.date]:
    return None if x is None else dt.date.fromisoformat(str(x)[:10])


def _time(x) -> Optional[dt.datetime]:
    if x is None:
        return None
    return dt.datetime.strptime(x, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)


def _weights_body(weights) -> dict:
    """Weights from a dict, a polars or pandas DataFrame with ``ticker`` and ``weight``
    columns, or a pandas Series indexed by ticker."""
    if hasattr(weights, "columns") and (hasattr(weights, "to_dicts") or hasattr(weights, "to_dict")):
        if not {"ticker", "weight"} <= set(weights.columns):
            raise ValueError("A weights DataFrame needs columns 'ticker' and 'weight'.")
        rows = weights.to_dicts() if hasattr(weights, "to_dicts") else weights.to_dict("records")
        weights = {row["ticker"]: row["weight"] for row in rows}
    elif not isinstance(weights, Mapping) and hasattr(weights, "to_dict"):
        weights = weights.to_dict()
    out = {}
    for ticker, weight in dict(weights).items():
        if not isinstance(ticker, str) or not ticker:
            raise ValueError("Weights need ticker names.")
        weight = float(weight)
        if not math.isfinite(weight):
            raise ValueError("Weights must be finite numbers.")
        out[ticker] = weight
    return out


def _as_of(as_of) -> str:
    if as_of is None:
        raise ValueError("Give as_of: the date of the last close your decision used.")
    if isinstance(as_of, dt.datetime):
        as_of = as_of.date()
    if isinstance(as_of, dt.date):
        return as_of.isoformat()
    return dt.date.fromisoformat(str(as_of)[:10]).isoformat()


ERRORS = {"code": pl.String, "ticker": pl.String, "message": pl.String}


@dataclass(repr=False)
class Check:
    """Result of ``validate()`` or ``submit()``."""

    ok: bool
    fill_date: Optional[dt.date]
    parameter_set_id: Optional[str]
    weights: dict
    errors: pl.DataFrame
    diagnostics: dict = field(default_factory=dict)
    submission_id: Optional[str] = None
    status: Optional[str] = None

    def __repr__(self) -> str:
        what = "Check" if self.status is None else f"Submission {self.submission_id} ({self.status})"
        lines = [f"{what}: {'OK' if self.ok else 'problems found'}"]
        if self.fill_date is not None:
            lines.append(f"Fill date: {self.fill_date.isoformat()}, rules {self.parameter_set_id}")
        d = self.diagnostics
        if d:
            lines.append(f"Positions {d.get('n_positions')}, gross {d.get('gross'):.3f}, net {d.get('net'):.3f}, cash {d.get('cash'):.3f}")
        if self.errors.height:
            lines.append("Errors:")
            for e in self.errors.iter_rows(named=True):
                ticker = f" {e['ticker']}" if e.get("ticker") else ""
                lines.append(f"  {e['code']}{ticker}: {e['message']}")
        return "\n".join(lines)


def _check(d: Mapping) -> Check:
    return Check(
        ok=bool(d.get("ok")),
        fill_date=_date(d.get("fill_date")),
        parameter_set_id=d.get("parameter_set_id"),
        weights=dict(d.get("weights") or {}),
        errors=_frame(d.get("errors"), ERRORS).select(list(ERRORS)),
        diagnostics=dict(d.get("diagnostics") or {}),
        submission_id=d.get("submission_id"),
        status=d.get("status"),
    )


def get_universe(as_of=None) -> pl.DataFrame:
    """Tickers as of a close (default: the latest). ``eligible`` ones can be bought,
    ``sp500`` marks S&P 500 members, ``as_of`` is the snapshot date."""
    json = _call("GET", "universe", params={"as_of": None if as_of is None else _as_of(as_of)})
    return _frame(json["data"]).with_columns(as_of=pl.lit(_date(json["as_of"]), dtype=pl.Date))


def get_calendar(start=None, end=None) -> pl.DataFrame:
    """Fill dates and their deadlines; ``is_next`` marks the next fill."""
    json = _call("GET", "calendar", params={
        "from": None if start is None else _as_of(start), "to": None if end is None else _as_of(end)
    })
    df = _frame(json["data"]["fills"], {"date": pl.String, "deadline": pl.String})
    return df.with_columns(is_next=pl.col("date") == pl.lit(_date(json["data"].get("next_fill")), dtype=pl.Date))


def get_parameters() -> pl.DataFrame:
    """Rule sets by ``effective_from``; ``applies_next`` marks the set in effect at the next fill."""
    json = _call("GET", "parameters")
    df = _frame(json["data"]["sets"])
    return df.with_columns(applies_next=pl.col("set_id") == pl.lit(json.get("parameter_set_id"), dtype=pl.String))


def get_benchmarks() -> dict:
    """Naive 1/N and buy and hold over the S&P 500, and SPY: ``summary`` and ``series``."""
    d = _call("GET", "benchmarks")["data"]
    return {"summary": _frame(d.get("summary")), "series": _frame(d.get("series"))}


def validate(weights, as_of, rationale: Optional[str] = None) -> Check:
    """Run every check the simulation would run, without storing anything."""
    json = _call("POST", "validate", body={"as_of": _as_of(as_of), "weights": _weights_body(weights), "rationale": rationale})
    return _check(json["data"])


def submit(weights, as_of, rationale: Optional[str] = None) -> Check:
    """Submit target weights for the next fill. ``rationale`` is required: it is your
    decision log. A rejected submission is kept, returned and warned about."""
    json = _call("POST", "submit", ok=(201, 422),
                 body={"as_of": _as_of(as_of), "weights": _weights_body(weights), "rationale": rationale})
    out = _check(json["data"])
    if not out.ok:
        warnings.warn("Submission rejected: " + ", ".join(dict.fromkeys(out.errors["code"])), stacklevel=2)
    return out


def cancel(submission_id: str) -> dict:
    """Withdraw a submission before its deadline."""
    d = _call("DELETE", f"submit/{submission_id}")["data"]
    return {"submission_id": d["submission_id"], "cancelled_at": _time(d.get("cancelled_at")), "fill_date": _date(d.get("fill_date"))}


def get_submissions() -> pl.DataFrame:
    """Your submissions, newest first; ``weights`` is a list of ``{ticker, weight}`` per row."""
    records = _call("GET", "submissions")["data"]
    for r in records or []:
        r["weights"] = [{"ticker": k, "weight": float(v)} for k, v in (r.get("weights") or {}).items()]
    return _frame(records, {"weights": WEIGHTS} if records else None)


def get_portfolio() -> dict:
    """Positions and cash at the latest close: ``date``, ``nav``, ``cash``, ``positions``."""
    d = _call("GET", "portfolio")["data"]
    return {"date": _date(d.get("date")), "nav": d.get("nav"), "cash": d.get("cash"), "positions": _frame(d.get("positions"))}


def get_performance() -> dict:
    """Your statistics (``summary``), the bots' (``benchmarks``) and your daily NAV (``series``)."""
    d = _call("GET", "performance")["data"]
    return {"summary": _frame(d.get("summary")), "benchmarks": _frame(d.get("benchmarks")), "series": _frame(d.get("series"))}


def get_leaderboard() -> pl.DataFrame:
    """Every team's statistics under pseudonyms; ``you`` marks your row."""
    return _frame(_call("GET", "leaderboard")["data"])
