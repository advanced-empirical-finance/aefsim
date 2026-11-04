"""Functions mirroring the R package aefsim: same names, same columns."""

from __future__ import annotations

import math
import os
import time
import warnings
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

import pandas as pd
import requests

VERSION = "0.1.0"
DEFAULT_URL = "https://eumel.tail81c88a.ts.net/aef"
DATE_COLS = {"date", "as_of", "fill_date", "effective_from", "delisted_on", "start", "end", "next_fill"}
TIME_COLS = {"submitted_at", "deadline", "cancelled_at", "next_deadline", "time"}


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
            time.sleep(2 ** attempt)
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


def _frame(records) -> pd.DataFrame:
    df = pd.DataFrame.from_records(records or [])
    for col in df.columns:
        if col in DATE_COLS:
            df[col] = pd.to_datetime(df[col], errors="coerce")
        elif col in TIME_COLS:
            df[col] = pd.to_datetime(df[col], utc=True, errors="coerce")
    return df


def _date(x):
    return None if x is None else pd.Timestamp(x)


def _time(x):
    if x is None:
        return None
    t = pd.Timestamp(x)
    return t.tz_convert("UTC") if t.tzinfo else t.tz_localize("UTC")


def _weights_body(weights) -> dict:
    if hasattr(weights, "to_dicts") and hasattr(weights, "columns"):  # a polars DataFrame
        if not {"ticker", "weight"} <= set(weights.columns):
            raise ValueError("A weights DataFrame needs columns 'ticker' and 'weight'.")
        weights = {row["ticker"]: row["weight"] for row in weights.to_dicts()}
    elif isinstance(weights, pd.DataFrame):
        if not {"ticker", "weight"} <= set(weights.columns):
            raise ValueError("A weights DataFrame needs columns 'ticker' and 'weight'.")
        weights = dict(zip(weights["ticker"], weights["weight"]))
    elif isinstance(weights, pd.Series):
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
    return pd.Timestamp(as_of).strftime("%Y-%m-%d")


@dataclass(repr=False)
class Check:
    """Result of ``validate()`` or ``submit()``."""

    ok: bool
    fill_date: Optional[pd.Timestamp]
    parameter_set_id: Optional[str]
    weights: dict
    errors: pd.DataFrame
    diagnostics: dict = field(default_factory=dict)
    submission_id: Optional[str] = None
    status: Optional[str] = None

    def __repr__(self) -> str:
        what = "Check" if self.status is None else f"Submission {self.submission_id} ({self.status})"
        lines = [f"{what}: {'OK' if self.ok else 'problems found'}"]
        if self.fill_date is not None:
            lines.append(f"Fill date: {self.fill_date:%Y-%m-%d}, rules {self.parameter_set_id}")
        d = self.diagnostics
        if d:
            lines.append(f"Positions {d.get('n_positions')}, gross {d.get('gross'):.3f}, net {d.get('net'):.3f}, cash {d.get('cash'):.3f}")
        if len(self.errors):
            lines.append("Errors:")
            for _, e in self.errors.iterrows():
                ticker = f" {e['ticker']}" if isinstance(e.get("ticker"), str) else ""
                lines.append(f"  {e['code']}{ticker}: {e['message']}")
        return "\n".join(lines)


def _check(d: Mapping) -> Check:
    errors = _frame(d.get("errors"))
    if errors.empty:
        errors = pd.DataFrame(columns=["code", "ticker", "message"])
    return Check(
        ok=bool(d.get("ok")),
        fill_date=_date(d.get("fill_date")),
        parameter_set_id=d.get("parameter_set_id"),
        weights=dict(d.get("weights") or {}),
        errors=errors,
        diagnostics=dict(d.get("diagnostics") or {}),
        submission_id=d.get("submission_id"),
        status=d.get("status"),
    )


def get_universe(as_of=None) -> pd.DataFrame:
    """Tickers as of a close (default: the latest): ``eligible`` ones can be bought,
    ``sp500`` marks S&P 500 members. The snapshot date is in ``.attrs["as_of"]``."""
    json = _call("GET", "universe", params={"as_of": None if as_of is None else _as_of(as_of)})
    df = _frame(json["data"])
    df.attrs["as_of"] = _date(json["as_of"])
    return df


def get_calendar(start=None, end=None) -> pd.DataFrame:
    """Fill dates and deadlines; ``.attrs`` has ``next_fill`` and ``next_deadline``."""
    json = _call("GET", "calendar", params={
        "from": None if start is None else _as_of(start), "to": None if end is None else _as_of(end)
    })
    df = _frame(json["data"]["fills"])
    df.attrs["next_fill"] = _date(json["data"].get("next_fill"))
    df.attrs["next_deadline"] = _time(json["data"].get("next_deadline"))
    return df


def get_parameters() -> pd.DataFrame:
    """Rule sets by ``effective_from``; ``.attrs`` has ``next_fill`` and ``parameter_set_id``."""
    json = _call("GET", "parameters")
    df = _frame(json["data"]["sets"])
    df.attrs["next_fill"] = _date(json["data"].get("next_fill"))
    df.attrs["parameter_set_id"] = json.get("parameter_set_id")
    return df


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


def get_submissions() -> pd.DataFrame:
    """Your submissions, newest first; ``weights`` holds a dict per row."""
    df = _frame(_call("GET", "submissions")["data"])
    if "weights" in df.columns:
        df["weights"] = [dict(w) if isinstance(w, Mapping) else {} for w in df["weights"]]
    return df


def get_portfolio() -> dict:
    """Positions and cash at the latest close: ``date``, ``nav``, ``cash``, ``positions``."""
    d = _call("GET", "portfolio")["data"]
    return {"date": _date(d.get("date")), "nav": d.get("nav"), "cash": d.get("cash"), "positions": _frame(d.get("positions"))}


def get_performance() -> dict:
    """Your statistics (``summary``), the bots' (``benchmarks``) and your daily NAV (``series``)."""
    d = _call("GET", "performance")["data"]
    return {"summary": _frame(d.get("summary")), "benchmarks": _frame(d.get("benchmarks")), "series": _frame(d.get("series"))}


def get_leaderboard() -> pd.DataFrame:
    """Every team's statistics under pseudonyms; ``you`` marks your row."""
    return _frame(_call("GET", "leaderboard")["data"])
