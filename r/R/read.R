#' Read the universe, calendar, rules and benchmarks
#'
#' @param as_of Date of a close; the default is the latest one.
#' @param start,end First and last fill date; default the whole semester.
#' @return
#' * `get_universe()`: a tibble of `ticker`, `name`, `exchange`, `eligible`,
#'   `sp500`, `delisted_on` and `as_of`, the snapshot date. Only `eligible`
#'   tickers can be bought.
#' * `get_calendar()`: a tibble of fill dates and deadlines; `is_next` marks
#'   the next fill.
#' * `get_parameters()`: a tibble of rule sets by `effective_from`;
#'   `applies_next` marks the set in effect at the next fill.
#' * `get_benchmarks()`: a list of `summary` and `series` tibbles.
#' @export
get_universe <- function(as_of = NULL) {
  json <- api_call("GET", "universe", query = list(as_of = if (!is.null(as_of)) format(as.Date(as_of))))
  x <- as_tbl(json$data)
  x[["as_of"]] <- rep(as_date1(json$as_of), nrow(x))
  x
}

#' @rdname get_universe
#' @export
get_calendar <- function(start = NULL, end = NULL) {
  json <- api_call("GET", "calendar", query = list(
    from = if (!is.null(start)) format(as.Date(start)), to = if (!is.null(end)) format(as.Date(end))
  ))
  x <- as_tbl(json$data$fills)
  x[["is_next"]] <- x[["date"]] %in% as_date1(json$data$next_fill)
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
