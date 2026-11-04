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

The functions have the same names and return the same columns in R and Python.

### Dates: what `as_of` means

`as_of` is always a date, such as `"2027-03-01"`: the trading day whose closing prices your decision is based on. You decide after a US close, so on a normal day `as_of` is that day, and your order is filled at the next morning's open. Every table the client returns also has an `as_of` column: the close the data reflects.

### Before you trade

| Function | What you get |
|---|---|
| `get_universe(as_of)` | Every stock in the simulation, one row per ticker, as it stood at one close (leave out `as_of` for the latest): `ticker`, `name`, `exchange`, `eligible` (you may buy it), `sp500` (it is in the S&P 500) and `delisted_on`. |
| `get_calendar()` | Every day of the semester on which orders are filled, one row per day: `date` and `deadline`, the moment your order for that day must be in (09:00 New York time, usually 15:00 in Copenhagen; the column is in UTC). US market holidays have no fill. `is_next` marks the next fill. |
| `get_parameters()` | The trading rules, one row per rule set: transaction costs, shorting, the leverage limit, the borrow fee, the maximum number of positions, and `effective_from`, the first fill the set applies to. The rules change twice: costs from 1 March, shorting from 5 April. `applies_next` marks the set for the next fill. |

**`eligible`.** The universe also lists stocks you may not buy, so you can still look up one you hold. A stock is eligible if it closed at $5 or more on `as_of` and has not been delisted. If a stock you hold stops being eligible, you may keep it or sell it, but not buy more.

**`sp500`.** Two of the three benchmarks hold the S&P 500 stocks. Filter on `sp500` to choose from the same stocks.

### Trading

| Function | What it does |
|---|---|
| `validate(weights, as_of, rationale)` | Checks a portfolio without sending it. You get the fill date, the rule set that will apply and every problem found, such as an ineligible ticker, too many positions, too much leverage or a missed deadline. Nothing is stored. |
| `submit(weights, as_of, rationale)` | Sends your target portfolio for the next fill. It runs the same checks; a rejected submission is stored too, with its errors. You may submit several times before the deadline: the last accepted one is filled. Without a submission, your portfolio stays as it is. |
| `cancel(submission_id)` | Withdraws a submission before its deadline. |

### Results

| Function | What you get |
|---|---|
| `get_submissions()` | All your submissions, newest first: when you sent them, `as_of`, status (accepted or rejected), weights, rationale, fill date, and whether each was filled or cancelled. |
| `get_portfolio()` | Your portfolio at the latest close: NAV, cash, and every position with shares, price, value and weight. |
| `get_performance()` | Your daily NAV (`series`) and your return, volatility, Sharpe ratio, maximum drawdown, turnover and costs (`summary`), with the same statistics for the benchmarks (`benchmarks`). |
| `get_leaderboard()` | Return, volatility, Sharpe ratio and maximum drawdown for every team and benchmark, under pseudonyms. `you` marks your team. |
| `get_benchmarks()` | The three benchmark portfolios: naive 1/N (equal weights in the eligible S&P 500 stocks, rebalanced at every fill), buy and hold (the same stocks, bought at the first fill and then held) and the market (the SPY fund, held). |

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
