# aefsim

Clients for the trading simulation in Advanced Empirical Finance (University of Copenhagen, spring 2027). Your team submits target portfolio weights; the simulation fills them at the next US open, charges costs and marks your portfolio to market every day. These packages wrap the simulation's API, with the same functions in R and Python.

Prices are not part of the API: download them yourself, for example with [tidyfinance](https://www.tidy-finance.org), which uses the same Yahoo Finance data as the simulation.

## Install

R:

```r
install.packages("pak")
pak::pak("advanced-empirical-finance/aefsim/r")
```

Python, with [uv](https://docs.astral.sh/uv/) in your project, or with pip:

```sh
uv add "git+https://github.com/advanced-empirical-finance/aefsim#subdirectory=python"
pip install "git+https://github.com/advanced-empirical-finance/aefsim#subdirectory=python"
```

## Your token

Each team gets one token. Keep it out of your code and out of Git: put it in an environment variable.

- R: add `AEF_TOKEN=aef_...` to `~/.Renviron` (`usethis::edit_r_environ()`), then restart R.
- Python: `export AEF_TOKEN=aef_...` in your shell, or a `.env` file you never commit.

`set_token()` sets it for the current session instead.

## Functions

| Function | What it does |
|---|---|
| `set_token(token)`, `set_url(url)` | connection settings (defaults: `AEF_TOKEN`, the course server) |
| `get_universe(as_of)` | tickers you may trade as of a close: `eligible`, `sp500`, and the snapshot date `as_of` |
| `get_calendar()` | fill dates and deadlines (09:00 New York time); `is_next` marks the next fill |
| `get_parameters()` | the rules: costs, shorting, leverage, position cap, and when they change; `applies_next` marks the set for the next fill |
| `validate(weights, as_of, rationale)` | check a submission without sending it |
| `submit(weights, as_of, rationale)` | send it; the last accepted one before the deadline is filled |
| `cancel(submission_id)` | withdraw it before the deadline |
| `get_submissions()` | your submissions, with status, fills and cancellations |
| `get_portfolio()` | your positions and cash at the latest close |
| `get_performance()` | your NAV series and statistics, next to the benchmarks |
| `get_leaderboard()` | all teams under pseudonyms |
| `get_benchmarks()` | naive 1/N and buy and hold over the S&P 500, and SPY |

`weights` maps tickers to target weights: a named vector or a data frame with `ticker` and `weight` in R; a dict or a polars (or pandas) DataFrame with `ticker` and `weight` in Python. R returns tibbles, Python returns polars DataFrames (like tidyfinance), with the same column names. The rest of your book sits in cash. `as_of` is the date of the last close your decision used. Every submission needs a `rationale`: it is your decision log.

## Quick start

```r
library(aefsim)
universe <- get_universe()
as_of <- max(universe$as_of)
weights <- c(AAPL = 0.2, MSFT = 0.2, JNJ = 0.1)
validate(weights, as_of = as_of)
submit(weights, as_of = as_of, rationale = "Three large caps, half the book in cash while I learn the ropes.")
```

```python
import aefsim
universe = aefsim.get_universe()
as_of = universe["as_of"].max()
weights = {"AAPL": 0.2, "MSFT": 0.2, "JNJ": 0.1}
aefsim.validate(weights, as_of=as_of)
aefsim.submit(weights, as_of=as_of, rationale="Three large caps, half the book in cash while I learn the ropes.")
```

The [notebooks](notebooks/) walk through a first submission in R and in Python.

## Development

- R package in `r/`: `testthat::test_local("r")`. The repository root is a [uvr](https://github.com/nbafrank/uvr) project for the development dependencies.
- Python package in `python/`: `cd python && uv sync && uv run pytest`.

Both packages are tested against canned API responses, so the tests need neither a token nor the network.

## Licence

MIT, see [LICENSE](LICENSE).
