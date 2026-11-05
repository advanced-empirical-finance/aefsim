#' Read the universe, calendar, rules and benchmarks
#'
#' @param close_date Date of a close; the default is the latest one.
#' @param start,end First and last trading day; default the whole semester.
#' @return
#' * `get_universe()`: a tibble of the stocks you can buy after that close:
#'   `ticker`, `permno` (CRSP's permanent number, for joining CRSP data),
#'   `name`, `exchange`, `sp500` (member of the S&P 500) and `close_date`.
#' * `get_calendar()`: a tibble of trading days (`date`) and the deadline
#'   for each; `is_next` marks the next one.
#' * `get_parameters()`: a tibble of rule sets by `effective_from`;
#'   `applies_next` marks the set in effect for the next trade.
#' * `get_benchmarks()`: a list of `summary` and `series` tibbles.
#' @export
get_universe <- function(close_date = NULL) {
  json <- api_call("GET", "universe", query = list(close_date = if (!is.null(close_date)) close_date_string(close_date)))
  x <- as_tbl(json$data)
  if (!nrow(x)) x <- tibble::tibble(ticker = character(), permno = integer(), name = character(), exchange = character(), sp500 = logical())
  if ("permno" %in% names(x)) x$permno <- as.integer(x$permno)
  x[["close_date"]] <- rep(as_date1(json$close_date), nrow(x))
  x
}

#' @rdname get_universe
#' @export
get_calendar <- function(start = NULL, end = NULL) {
  json <- api_call("GET", "calendar", query = list(
    from = if (!is.null(start)) date_string(start, "start"), to = if (!is.null(end)) date_string(end, "end")
  ))
  x <- as_tbl(json$data$trading_days)
  x[["is_next"]] <- x[["date"]] %in% as_date1(json$data$next_trade_date)
  x
}

#' @rdname get_universe
#' @export
get_parameters <- function() {
  json <- api_call("GET", "parameters")
  x <- as_tbl(json$data$sets)
  x[["applies_next"]] <- x[["set_id"]] %in% json$parameter_set_id
  x
}

#' @rdname get_universe
#' @export
get_benchmarks <- function() {
  json <- api_call("GET", "benchmarks")
  list(summary = as_tbl(json$data$summary), series = as_tbl(json$data$series))
}
