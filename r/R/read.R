#' Read the universe, calendar, rules and benchmarks
#'
#' @param as_of Date of a close; the default is the latest one.
#' @param start,end First and last fill date; default the whole semester.
#' @return
#' * `get_universe()`: a tibble of `ticker`, `name`, `exchange`, `eligible`,
#'   `sp500` and `delisted_on`, with the snapshot date as attribute `as_of`.
#'   Only `eligible` tickers can be bought.
#' * `get_calendar()`: a tibble of fill dates and deadlines, with attributes
#'   `next_fill` and `next_deadline`.
#' * `get_parameters()`: a tibble of rule sets by `effective_from`, with
#'   attribute `next_fill` and `parameter_set_id` (the set in effect then).
#' * `get_benchmarks()`: a list of `summary` and `series` tibbles.
#' @export
get_universe <- function(as_of = NULL) {
  json <- api_call("GET", "universe", query = list(as_of = if (!is.null(as_of)) format(as.Date(as_of))))
  structure(as_tbl(json$data), as_of = as_date1(json$as_of))
}

#' @rdname get_universe
#' @export
get_calendar <- function(start = NULL, end = NULL) {
  json <- api_call("GET", "calendar", query = list(
    from = if (!is.null(start)) format(as.Date(start)), to = if (!is.null(end)) format(as.Date(end))
  ))
  structure(
    as_tbl(json$data$fills),
    next_fill = as_date1(json$data$next_fill),
    next_deadline = parse_time(json$data$next_deadline %||% NA_character_)
  )
}

#' @rdname get_universe
#' @export
get_parameters <- function() {
  json <- api_call("GET", "parameters")
  structure(as_tbl(json$data$sets), next_fill = as_date1(json$data$next_fill), parameter_set_id = json$parameter_set_id)
}

#' @rdname get_universe
#' @export
get_benchmarks <- function() {
  json <- api_call("GET", "benchmarks")
  list(summary = as_tbl(json$data$summary), series = as_tbl(json$data$series))
}
