"""Functions mirroring the R package aefsim: same names, same columns, same messages."""

from __future__ import annotations

import datetime as dt
import math
import os
import re
import sys
import time
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional

import polars as pl
import requests

VERSION = "0.3.0"
DEFAULT_URL = "https://eumel.tail81c88a.ts.net/aef"
RETRY_WAIT = 1.0  # seconds before the first retry of a GET; doubles each time
DATE_COLS = {"date", "close_date", "trade_date", "effective_from", "delisted_on", "start", "end", "next_trade_date"}
TIME_COLS = {"submitted_at", "deadline", "cancelled_at", "next_deadline", "time"}
WEIGHTS = pl.List(pl.Struct({"ticker": pl.String, "weight": pl.Float64}))
POSITIONS = pl.List(pl.Struct({"ticker": pl.String, "shares": pl.Float64, "price": pl.Float64,
                               "value": pl.Float64, "weight": pl.Float64, "stale": pl.Boolean}))

# Messages the client writes itself, word for word the same as in the R
# package (r/R/messages.R); only the example differs. Errors from the server
# arrive with their own message.
MSG = {
    "missing_token": "No team token. Run set_token() once to save it, or set the environment variable AEF_TOKEN.",
    "token_noninteractive": "set_token() asks for your token, which needs an interactive session. In a script, use set_token(\"aef_...\") or set the environment variable AEF_TOKEN.",
    "token_invalid": "That is not a simulation token: team tokens start with aef_.",
    "ask_token": "Paste your team's token (it starts with aef_): ",
    "ask_where": "Where do you want to save it? Enter 'project' for %s in this project's folder or 'home' for your home folder: ",
    "ask_replace": "%s already holds a token. Do you want to replace it? Enter 'yes' or 'no': ",
    "ask_gitignore": "Do you want to add %s to .gitignore, so your token never ends up in Git? It is highly recommended! Enter 'yes' or 'no': ",
    "gitignore_added": "%s added to .gitignore.",
    "gitignore_not_added": "%s NOT added to .gitignore.",
    "token_saved": "Your token is saved in %s and set for this session.",
    "token_not_saved": "Not saved: the token is set for this session only. Run set_token() again to save it.",
    "connection_failed": "Could not reach the simulation server at %s. Check your internet connection and try again; if it stays unreachable, tell the course team.",
    "timeout": "The simulation server at %s did not answer within 60 seconds. Try again in a few minutes.",
    "timeout_write": " Your submission may have arrived anyway: check get_submissions() before you submit again.",
    "server_unavailable": "The simulation server at %s is not responding (HTTP %d). It may be restarting: try again in a few minutes, and tell the course team if it stays down.",
    "http_error": "Unexpected answer from the simulation server at %s (HTTP %d).",
    "which_server": " (server: %s)",
    "close_date_missing": "Give close_date: the date of the close your decision is based on, such as \"2027-03-01\".",
    "date_invalid": "%s must be a date in the form YYYY-MM-DD, such as \"2027-03-01\", not \"%s\".",
    "weights_columns": "weights needs the columns ticker and weight, such as %s.",
    "weights_tickers": "Every weight needs a ticker, such as %s.",
    "weights_numbers": "Each weight must be one finite number; check %s.",
    "weights_duplicates": "Each ticker may appear only once in weights; check %s.",
    "submission_id": "Give submission_id: the id submit() returned, or one from get_submissions().",
    "rejected": "Submission %s was rejected and will not trade:",
}
WEIGHTS_EXAMPLE = 'pl.DataFrame({"ticker": ["AAPL"], "weight": [0.1]})'


class AefsimError(Exception):
    """An error from the simulation or the client, with its ``code`` and HTTP
    ``status`` (None for problems the client catches before sending anything)."""

    def __init__(self, code: str, message: str, status: Optional[int] = None):
        super().__init__(f"{message} [{code}]")
        self.code = code
        self.message = message
        self.status = status


def set_token(token: Optional[str] = None) -> None:
    """Save your team's token so you never put it in code.

    Like tidyfinance's ``set_wrds_credentials()``, it asks for the token, then
    whether to save it in a ``.env`` file in this project's folder or in your
    home folder, and offers to add a project ``.env`` to ``.gitignore`` so the
    token never ends up in Git. The client reads ``.env`` by itself, so you run
    it once. In a script, pass the token instead (or set the environment
    variable AEF_TOKEN): ``set_token(token)`` sets it for the session without
    asking anything."""
    ask = token is None
    if ask:
        if not _is_interactive():
            raise AefsimError("missing_token", MSG["token_noninteractive"])
        token = input(MSG["ask_token"]).strip()
    if not isinstance(token, str) or not token.startswith("aef_"):
        raise AefsimError("invalid_token", MSG["token_invalid"])
    os.environ["AEF_TOKEN"] = token
    if ask:
        _store_token(token, ".env")


def _store_token(token: str, file: str) -> bool:
    """The dialogue behind set_token(), with the same prompts as the R package."""
    where = input(MSG["ask_where"] % file).strip().lower()
    folder = {"project": Path.cwd(), "home": _home()}.get(where)
    if folder is None:
        print(MSG["token_not_saved"])
        return False
    path = folder / file
    lines = path.read_text().splitlines() if path.exists() else []
    if any(line.startswith("AEF_TOKEN=") for line in lines) and not _yes(input(MSG["ask_replace"] % file)):
        print(MSG["token_not_saved"])
        return False
    lines = [line for line in lines if not line.startswith("AEF_TOKEN=")] + [f"AEF_TOKEN={token}"]
    path.write_text("\n".join(lines) + "\n")
    if where == "project":
        _ignore_file(folder, file)
    print(MSG["token_saved"] % path)
    return True


def _ignore_file(folder: Path, file: str) -> None:
    gitignore = folder / ".gitignore"
    lines = gitignore.read_text().splitlines() if gitignore.exists() else []
    if file in (line.strip() for line in lines) or f"/{file}" in (line.strip() for line in lines):
        return
    if _yes(input(MSG["ask_gitignore"] % file)):
        gitignore.write_text("\n".join(lines + [file]) + "\n")
        print(MSG["gitignore_added"] % file)
    else:
        print(MSG["gitignore_not_added"] % file)


def _yes(answer: str) -> bool:
    return answer.strip().lower() in ("yes", "y")


def _is_interactive() -> bool:
    return sys.stdin is not None and sys.stdin.isatty()


def _home() -> Path:
    return Path.home()


def _token() -> str:
    """AEF_TOKEN from the environment, else from .env in this folder, else from ~/.env."""
    token = os.environ.get("AEF_TOKEN", "")
    if token:
        return token
    for path in (Path.cwd() / ".env", _home() / ".env"):
        if path.exists():
            for line in path.read_text().splitlines():
                key, _, value = line.strip().removeprefix("export ").partition("=")
                if key.strip() == "AEF_TOKEN" and value.strip():
                    return value.strip().strip("'\"")
    return ""


def set_url(url: str) -> None:
    """Point the client at another server, for example a test one."""
    os.environ["AEF_URL"] = url.rstrip("/")


def _server_url() -> str:
    return os.environ.get("AEF_URL", DEFAULT_URL).rstrip("/")


def _call(method: str, path: str, body: Any = None, params: Optional[dict] = None, ok=(200,)):
    """One API call. GETs are retried on rate limits and gateway errors; writes are
    not, so a submission is never sent twice."""
    token = _token()
    if not token:
        raise AefsimError("missing_token", MSG["missing_token"])
    base = _server_url()
    headers = {"Authorization": f"Bearer {token}", "User-Agent": f"aefsim Python client {VERSION}"}
    params = {k: v for k, v in (params or {}).items() if v is not None} or None
    tries = 3 if method == "GET" else 1
    for attempt in range(tries):
        try:
            resp = requests.request(method, base + "/" + path, headers=headers, json=body, params=params, timeout=60)
        except requests.exceptions.Timeout:
            raise AefsimError("timeout", MSG["timeout"] % base + ("" if method == "GET" else MSG["timeout_write"])) from None
        except requests.exceptions.ConnectionError:
            raise AefsimError("connection_failed", MSG["connection_failed"] % base) from None
        if method == "GET" and resp.status_code in (429, 502, 503, 504) and attempt < tries - 1:
            time.sleep(RETRY_WAIT * 2 ** attempt)
            continue
        break
    try:
        payload = resp.json()
    except ValueError:
        payload = None
    status = resp.status_code
    if status not in ok:
        err = payload.get("error") if isinstance(payload, dict) else None
        if not isinstance(err, dict) or not err.get("code"):
            if status in (502, 503, 504):
                raise AefsimError("server_unavailable", MSG["server_unavailable"] % (base, status), status)
            raise AefsimError("http_error", MSG["http_error"] % (base, status), status)
        message = err.get("message") or ""
        if err["code"] in ("missing_token", "unknown_token"):
            message += MSG["which_server"] % base
        raise AefsimError(err["code"], message, status)
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


def _weights_frame(w) -> pl.DataFrame:
    """A JSON object of tickers and weights to a DataFrame of ``ticker`` and ``weight``."""
    w = dict(w or {})
    return pl.DataFrame({"ticker": list(w), "weight": [float(v) for v in w.values()]},
                        schema={"ticker": pl.String, "weight": pl.Float64})


def _bad_weights(which: str):
    raise AefsimError("malformed_weights", MSG[which] % WEIGHTS_EXAMPLE)


def _weights_body(weights) -> dict:
    """Weights from a polars or pandas DataFrame with ``ticker`` and ``weight``
    columns, a dict, or a pandas Series indexed by ticker."""
    if hasattr(weights, "columns") and (hasattr(weights, "to_dicts") or hasattr(weights, "to_dict")):
        if not {"ticker", "weight"} <= set(weights.columns):
            _bad_weights("weights_columns")
        rows = weights.to_dicts() if hasattr(weights, "to_dicts") else weights.to_dict("records")
        pairs = [(row["ticker"], row["weight"]) for row in rows]
    elif isinstance(weights, Mapping):
        pairs = list(weights.items())
    elif hasattr(weights, "to_dict"):
        pairs = list(weights.to_dict().items())
    else:
        _bad_weights("weights_columns")
    if any(not isinstance(t, str) or not t.strip() for t, _ in pairs):
        _bad_weights("weights_tickers")

    def finite(v):
        return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)

    bad = [t for t, v in pairs if not finite(v)]
    if bad:
        raise AefsimError("malformed_weights", MSG["weights_numbers"] % ", ".join(bad))
    keys = [t.strip().upper() for t, _ in pairs]
    dup = list(dict.fromkeys(k for i, k in enumerate(keys) if k in keys[:i]))
    if dup:
        raise AefsimError("duplicate_ticker", MSG["weights_duplicates"] % ", ".join(dup))
    return {t: float(v) for t, v in pairs}


def _date_string(x, name: str, code: str = "invalid_date") -> str:
    """A date argument as "YYYY-MM-DD": a date, a datetime or such a string."""
    if isinstance(x, dt.datetime):
        return x.date().isoformat()
    if isinstance(x, dt.date):
        return x.isoformat()
    if isinstance(x, str) and re.match(r"^\d{4}-\d{2}-\d{2}", x):
        try:
            return dt.date.fromisoformat(x[:10]).isoformat()
        except ValueError:
            pass
    raise AefsimError(code, MSG["date_invalid"] % (name, x))


def _close_date(close_date) -> str:
    if close_date is None:
        raise AefsimError("invalid_close_date", MSG["close_date_missing"])
    return _date_string(close_date, "close_date", "invalid_close_date")


ERRORS = {"code": pl.String, "ticker": pl.String, "message": pl.String}


def _error_lines(errors: pl.DataFrame) -> list:
    """'  ineligible_ticker PENNY: Not eligible on ...'"""
    return [f"  {e['code']}{' ' + e['ticker'] if e.get('ticker') else ''}: {e['message']}"
            for e in errors.iter_rows(named=True)]


@dataclass(repr=False)
class Check:
    """Result of ``validate()`` or ``submit()``."""

    ok: bool
    trade_date: Optional[dt.date]
    parameter_set_id: Optional[str]
    weights: pl.DataFrame
    errors: pl.DataFrame
    diagnostics: dict = field(default_factory=dict)
    submission_id: Optional[str] = None
    status: Optional[str] = None

    def __repr__(self) -> str:
        what = "Check" if self.status is None else f"Submission {self.submission_id} ({self.status})"
        lines = [f"{what}: {'OK' if self.ok else 'problems found'}"]
        if self.trade_date is not None:
            lines.append(f"Trades at the open on {self.trade_date.isoformat()} (rules {self.parameter_set_id})")
        d = self.diagnostics
        if d:
            lines.append(f"Positions {d.get('n_positions')}, gross {d.get('gross'):.3f}, net {d.get('net'):.3f}, cash {d.get('cash'):.3f}")
        if self.errors.height:
            lines.append("Errors:")
            lines.extend(_error_lines(self.errors))
        return "\n".join(lines)


def _check(d: Mapping) -> Check:
    return Check(
        ok=bool(d.get("ok")),
        trade_date=_date(d.get("trade_date")),
        parameter_set_id=d.get("parameter_set_id"),
        weights=_weights_frame(d.get("weights")),
        errors=_frame(d.get("errors"), ERRORS).select(list(ERRORS)),
        diagnostics=dict(d.get("diagnostics") or {}),
        submission_id=d.get("submission_id"),
        status=d.get("status"),
    )


def get_universe(close_date=None) -> pl.DataFrame:
    """The stocks you can buy after a close (default: the latest): ``ticker``,
    ``name``, ``exchange``, ``sp500`` (member of the S&P 500) and ``close_date``."""
    json = _call("GET", "universe", params={"close_date": None if close_date is None else _close_date(close_date)})
    schema = {"ticker": pl.String, "name": pl.String, "exchange": pl.String, "sp500": pl.Boolean}
    return _frame(json["data"], None if json["data"] else schema).with_columns(
        close_date=pl.lit(_date(json["close_date"]), dtype=pl.Date))


def get_calendar(start=None, end=None) -> pl.DataFrame:
    """Trading days (``date``) and the deadline for each; ``is_next`` marks the next one."""
    json = _call("GET", "calendar", params={
        "from": None if start is None else _date_string(start, "start"),
        "to": None if end is None else _date_string(end, "end"),
    })
    df = _frame(json["data"]["trading_days"], {"date": pl.String, "deadline": pl.String})
    return df.with_columns(is_next=pl.col("date") == pl.lit(_date(json["data"].get("next_trade_date")), dtype=pl.Date))


def get_parameters() -> pl.DataFrame:
    """Rule sets by ``effective_from``; ``applies_next`` marks the set in effect for the next trade."""
    json = _call("GET", "parameters")
    df = _frame(json["data"]["sets"])
    return df.with_columns(applies_next=pl.col("set_id") == pl.lit(json.get("parameter_set_id"), dtype=pl.String))


def get_benchmarks() -> dict:
    """Naive 1/N and buy and hold over the S&P 500, and SPY: ``summary`` and ``series``."""
    d = _call("GET", "benchmarks")["data"]
    return {"summary": _frame(d.get("summary")), "series": _frame(d.get("series"))}


def validate(weights, close_date=None, rationale: Optional[str] = None) -> Check:
    """Run every check the simulation would run, without storing anything."""
    body = {"close_date": _close_date(close_date), "weights": _weights_body(weights), "rationale": rationale}
    return _check(_call("POST", "validate", body=body)["data"])


def submit(weights, close_date=None, rationale: Optional[str] = None) -> Check:
    """Submit target weights. They trade at the next market open whose deadline
    (09:00 New York time) has not passed, so a submission after a deadline, over
    a weekend or before the start waits for the next open. ``rationale`` is
    required: it is your decision log. A rejected submission is kept, returned
    and warned about."""
    body = {"close_date": _close_date(close_date), "weights": _weights_body(weights), "rationale": rationale}
    out = _check(_call("POST", "submit", ok=(201, 422), body=body)["data"])
    if not out.ok:
        warnings.warn("\n".join([MSG["rejected"] % out.submission_id] + _error_lines(out.errors)), stacklevel=2)
    return out


def cancel(submission_id: str) -> dict:
    """Withdraw a submission before its deadline."""
    if not isinstance(submission_id, str) or not submission_id:
        raise AefsimError("invalid_submission_id", MSG["submission_id"])
    d = _call("DELETE", f"submit/{submission_id}")["data"]
    return {"submission_id": d["submission_id"], "cancelled_at": _time(d.get("cancelled_at")), "trade_date": _date(d.get("trade_date"))}


def get_submissions() -> pl.DataFrame:
    """Your submissions, newest first; ``weights`` is a list of ``{ticker, weight}`` per row."""
    records = _call("GET", "submissions")["data"]
    for r in records or []:
        r["weights"] = [{"ticker": k, "weight": float(v)} for k, v in (r.get("weights") or {}).items()]
    return _frame(records, {"weights": WEIGHTS} if records else None)


def get_portfolio() -> pl.DataFrame:
    """Your portfolio at the latest close, as one row: ``close_date``,
    ``portfolio_value`` (positions plus cash), ``cash`` and ``positions``, a list
    of ``{ticker, shares, price, value, weight, stale}``.
    ``get_portfolio().explode("positions").unnest("positions")`` gives one row per position."""
    d = _call("GET", "portfolio")["data"]
    def num(v):
        return None if v is None else float(v)

    positions = [{"ticker": p.get("ticker"), "shares": num(p.get("shares")), "price": num(p.get("price")),
                  "value": num(p.get("value")), "weight": num(p.get("weight")), "stale": p.get("stale")}
                 for p in d.get("positions") or []]
    return pl.DataFrame(
        {"close_date": [_date(d.get("close_date"))], "portfolio_value": [num(d.get("portfolio_value"))],
         "cash": [num(d.get("cash"))], "positions": [positions]},
        schema={"close_date": pl.Date, "portfolio_value": pl.Float64, "cash": pl.Float64, "positions": POSITIONS},
    )


def get_performance() -> dict:
    """Your statistics (``summary``), the benchmarks' (``benchmarks``) and your daily
    ``portfolio_value``, before and after costs (``series``)."""
    d = _call("GET", "performance")["data"]
    return {"summary": _frame(d.get("summary")), "benchmarks": _frame(d.get("benchmarks")), "series": _frame(d.get("series"))}


def get_leaderboard() -> pl.DataFrame:
    """Every team's statistics under pseudonyms; ``you`` marks your row."""
    return _frame(_call("GET", "leaderboard")["data"])
