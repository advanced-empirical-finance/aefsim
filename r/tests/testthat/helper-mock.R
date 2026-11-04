# Canned API responses keyed by "METHOD path". `seen` keeps the last
# request and counts calls. The same routes drive the Python tests.
seen <- new.env()
mock_api <- function(routes) {
  seen$n <- 0L
  function(req) {
    seen$n <- seen$n + 1L
    seen$req <- req
    path <- sub("\\?.*$", "", sub("^https?://[^/]+/aef/?", "", req$url))
    hit <- routes[[paste(req$method %||% "GET", path)]]
    if (is.null(hit)) hit <- list(status = 404L, body = list(error = list(code = "not_found", message = "No such endpoint.")))
    if (!is.null(hit$raw)) return(httr2::response(status_code = hit$status, body = charToRaw(hit$raw)))
    httr2::response_json(status_code = hit$status %||% 200L, body = hit$body)
  }
}
`%||%` <- function(x, y) if (is.null(x)) y else x

envelope <- function(data, close_date = "2027-02-09", set = "P1-baseline") {
  list(close_date = close_date, parameter_set_id = set, data = data)
}

check_ok <- list(
  ok = TRUE, trade_date = "2027-02-10", parameter_set_id = "P1-baseline", weights = list(AAPL = 0.3), errors = list(),
  diagnostics = list(gross = 0.3, net = 0.3, cash = 0.7, n_positions = 1L, max_abs_weight = 0.3)
)
check_bad <- list(
  ok = FALSE, submission_id = "team-01-x", status = "rejected", trade_date = "2027-02-10",
  parameter_set_id = "P1-baseline", weights = list(PENNY = 0.3),
  errors = list(list(code = "ineligible_ticker", ticker = "PENNY", message = "Not eligible on 2027-02-09.")),
  diagnostics = list(gross = 0.3, net = 0.3, cash = 0.7, n_positions = 1L, max_abs_weight = 0.3)
)
