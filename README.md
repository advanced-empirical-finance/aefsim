# aefsim

Clients for the trading simulation in Advanced Empirical Finance (University of Copenhagen, spring 2027). Your team submits target portfolio weights; the simulation trades them at the next US market open, charges costs and values your portfolio every day. These packages wrap the simulation's API, with the same functions in R and Python.

Prices are not part of the API: download them yourself, for example with [tidyfinance](https://www.tidy-finance.org), which uses the same Yahoo Finance data as the simulation.

## Install

In a terminal, in your project folder.

R, with [uvr](https://github.com/nbafrank/uvr) (version 0.4.8 or later):

```sh
uvr add advanced-empirical-finance/aefsim/r
```

Python, with [uv](https://docs.astral.sh/uv/):

```sh
uv add "git+https://github.com/advanced-empirical-finance/aefsim#subdirectory=python"
```

## Your token

Each team gets one token, starting with `aef_`. Run `set_token()` once and paste it when asked:

```r
aefsim::set_token()
```

```python
import aefsim
aefsim.set_token()
```

It asks where to save the token: `project` for this project's folder or `home` for your home folder. R saves it in `.Renviron`, Python in `.env`. For a project folder, it offers to add that file to `.gitignore`, so the token never ends up in Git. From then on the client finds the token by itself, in every new session too. R reads only one `.Renviron`: a project's replaces the one in your home folder.

In a script that runs without you, set the environment variable `AEF_TOKEN` instead, or call `set_token("aef_...")`, which asks nothing.

## How trading works

You decide after a US market close, with data up to that close. Then you submit target weights: what fraction of your portfolio's value each stock should have. They trade at the next market open whose deadline has not passed. The deadline is 09:00 New York time, usually 15:00 in Copenhagen, on the trading day itself.

- Submit whenever you like. A submission sent after a deadline, over a weekend or before the simulation starts waits for the next open.
- Submit as often as you like: the last accepted submission before a deadline is the one that trades.
- Without a new submission, your portfolio stays as it is.

`close_date` is always a date, such as `"2027-03-01"`: the day of the close your decision is based on. Usually that is the latest close, `max(get_universe()$close_date)`. Every table the client returns also has a `close_date` column: the close the data reflects. `trade_date` is the day of the open at which a submission trades.

## Functions

The functions have the same names and return the same columns in R and Python. R returns tibbles, Python polars DataFrames (like tidyfinance).

### Before you trade

| Function | What you get |
|---|---|
| `get_universe(close_date)` | The stocks you can buy after one close (leave out `close_date` for the latest), one row per stock: `ticker`, `name`, `exchange`, `sp500` (it is in the S&P 500) and `close_date`. |
| `get_calendar()` | Every trading day of the semester, one row per day: `date` and `deadline`, the moment your weights for that day's open must be in (the column is in UTC). US market holidays are not trading days. `is_next` marks the next one. |
| `get_parameters()` | The trading rules, one row per rule set: transaction costs, shorting, the leverage limit, the borrow fee, and `effective_from`, the first trading day the set applies to. The rules change twice: costs from 1 March, shorting from 5 April. `applies_next` marks the set for the next trade. |

The universe holds common stocks on NYSE, NYSE American and Nasdaq that closed at $5 or more on that day. If a stock you hold drops out, you may keep it or sell it, but not buy more; it still shows in `get_portfolio()`. Two of the three benchmarks hold the S&P 500 stocks: filter on `sp500` to choose from the same stocks.

### Trading

| Function | What it does |
|---|---|
| `validate(weights, close_date, rationale)` | Checks a portfolio without sending it. You get the trade date, the rule set that will apply and every problem found, such as an unknown ticker, an ineligible stock or too much leverage. Nothing is stored. |
| `submit(weights, close_date, rationale)` | Sends your target portfolio. It runs the same checks; a rejected submission is stored too, with its errors, and does not trade. |
| `cancel(submission_id)` | Withdraws a submission before its deadline. |

`weights` is a data frame with the columns `ticker` and `weight`: a tibble in R, a polars (or pandas) DataFrame in Python. A named vector in R or a dict in Python works too. Stocks you leave out get weight zero; whatever does not add up to one stays in cash. Every submission needs a `rationale`, a few sentences on why: it is your decision log.

### Results

| Function | What you get |
|---|---|
| `get_submissions()` | All your submissions, newest first: when you sent them, `close_date`, `trade_date`, status (accepted or rejected), the weights, the rationale, and whether each was `traded` or `cancelled`. |
| `get_portfolio()` | Your portfolio at the latest close, as one row: `close_date`, `portfolio_value` (positions plus cash), `cash` and `positions`, with shares, price, value and weight per stock. |
| `get_performance()` | Your daily `portfolio_value` before and after costs (`series`) and your return, volatility, Sharpe ratio, maximum drawdown, turnover and costs (`summary`), with the same statistics for the benchmarks (`benchmarks`). |
| `get_leaderboard()` | Return, volatility, Sharpe ratio and maximum drawdown for every team and benchmark, under pseudonyms. `you` marks your team. |
| `get_benchmarks()` | The three benchmark portfolios: naive 1/N (equal weights in the S&P 500 stocks of the universe, rebalanced every day), buy and hold (the same stocks, bought at the first trade and then held) and the market (the SPY fund, held). |

Results are updated once a night, after the US close: a trade at Tuesday's open shows up on Wednesday morning, Copenhagen time.

## Quick start

```r
library(aefsim)
universe <- get_universe()
close_date <- max(universe$close_date)
weights <- tibble::tibble(ticker = c("AAPL", "MSFT", "JNJ"), weight = c(0.2, 0.2, 0.1))
validate(weights, close_date = close_date)
submit(weights, close_date = close_date, rationale = "Three large caps, half the book in cash while I learn the ropes.")
```

```python
import aefsim
import polars as pl
universe = aefsim.get_universe()
close_date = universe["close_date"].max()
weights = pl.DataFrame({"ticker": ["AAPL", "MSFT", "JNJ"], "weight": [0.2, 0.2, 0.1]})
aefsim.validate(weights, close_date=close_date)
aefsim.submit(weights, close_date=close_date, rationale="Three large caps, half the book in cash while I learn the ropes.")
```

The course homepage's [Getting started](https://aef-course.ku.dk/simulation/getting-started.html) guide walks through a first submission in R and Python, from prices to the next morning.

## When something goes wrong

Every error says what went wrong and what to do, and ends with a code in brackets, such as `[unknown_ticker]`. The same problem gives the same message in R and Python. A rejected submission is not an error: `submit()` returns it with a warning that lists every problem, and `validate()` shows the same list. To handle errors in code, catch `aefsim_error` in R (`tryCatch(..., aefsim_error = function(e) e$code)`) or `aefsim.AefsimError` in Python (`e.code`).

## Development

- R package in `r/`: `testthat::test_local("r")`. The repository root is a [uvr](https://github.com/nbafrank/uvr) project for the development dependencies.
- Python package in `python/`: `cd python && uv sync && uv run pytest`.

Both packages are tested against canned API responses, so the tests need neither a token nor the network. The two test suites run the same scenarios, and the messages the clients write themselves are word for word the same.

## Licence

MIT, see [LICENSE](LICENSE).
