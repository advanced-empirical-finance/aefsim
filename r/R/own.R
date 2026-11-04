#' Your portfolio, submissions, performance and the leaderboard
#'
#' Results are updated once a night, after the US close: a fill at
#' Tuesday's open shows up on Wednesday morning (Copenhagen time).
#'
#' @return
#' * `get_portfolio()`: a list of `date`, `nav`, `cash` and `positions`
#'   (a tibble of `ticker`, `shares`, `price`, `value`, `weight`, `stale`).
#' * `get_submissions()`: a tibble, newest first, with `status`,
#'   `fill_date`, `cancelled`, `filled`, `rationale` and the `weights` as a
#'   list column of named vectors.
#' * `get_performance()`: a list of `summary` (return, volatility, Sharpe
#'   ratio with standard error, drawdown, turnover, costs), `benchmarks`
#'   (the same for the bots) and `series` (daily NAV).
#' * `get_leaderboard()`: a tibble of every team's statistics under
#'   pseudonyms; `you` marks your row, `rank` is by Sharpe ratio among teams.
#' @export
get_portfolio <- function() {
  json <- api_call("GET", "portfolio")
  d <- json$data
  list(date = as_date1(d$date), nav = d$nav, cash = d$cash, positions = as_tbl(d$positions))
}

#' @rdname get_portfolio
#' @export
get_submissions <- function() {
  json <- api_call("GET", "submissions")
  x <- as_tbl(json$data, lists = "weights")
  if ("weights" %in% names(x)) {
    x$weights <- lapply(x$weights, function(w) if (length(w)) unlist(w) else stats::setNames(numeric(0), character(0)))
  }
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
