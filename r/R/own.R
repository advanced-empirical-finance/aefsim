#' Your portfolio, submissions, performance and the leaderboard
#'
#' Results are updated once a night, after the US close: a trade at
#' Tuesday's open shows up on Wednesday morning (Copenhagen time).
#'
#' @return
#' * `get_portfolio()`: a one-row tibble of `close_date`, `portfolio_value`
#'   (positions plus cash), `cash` and `positions`, a list column holding a
#'   tibble of `ticker`, `shares`, `price`, `value`, `weight` and `stale`.
#'   `tidyr::unnest(get_portfolio(), positions)` gives one row per position.
#' * `get_submissions()`: a tibble, newest first, with `close_date`,
#'   `trade_date`, `status`, `cancelled`, `traded`, `rationale` and the
#'   `weights` as a list column of tibbles (`ticker`, `weight`).
#' * `get_performance()`: a list of `summary` (return, volatility, Sharpe
#'   ratio with standard error, drawdown, turnover, costs), `benchmarks`
#'   (the same for the benchmarks) and `series` (your daily
#'   `portfolio_value`, before and after costs).
#' * `get_leaderboard()`: a tibble of every team's statistics under
#'   pseudonyms; `you` marks your row, `rank` is by Sharpe ratio among teams.
#' @export
get_portfolio <- function() {
  d <- api_call("GET", "portfolio")$data
  positions <- as_tbl(d$positions)
  if (!nrow(positions)) {
    positions <- tibble::tibble(ticker = character(), shares = numeric(), price = numeric(),
                                value = numeric(), weight = numeric(), stale = logical())
  }
  tibble::tibble(
    close_date = as_date1(d$close_date), portfolio_value = as.numeric(d$portfolio_value),
    cash = as.numeric(d$cash), positions = list(positions)
  )
}

#' @rdname get_portfolio
#' @export
get_submissions <- function() {
  json <- api_call("GET", "submissions")
  x <- as_tbl(json$data, lists = "weights")
  if ("weights" %in% names(x)) x$weights <- lapply(x$weights, weights_tbl)
  x
}

#' @rdname get_portfolio
#' @export
get_performance <- function() {
  json <- api_call("GET", "performance")
  d <- json$data
  list(summary = as_tbl(d$summary), benchmarks = as_tbl(d$benchmarks), series = as_tbl(d$series))
}

#' @rdname get_portfolio
#' @export
get_leaderboard <- function() {
  as_tbl(api_call("GET", "leaderboard")$data)
}
