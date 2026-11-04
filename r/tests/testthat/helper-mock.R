# Canned API responses; `seen` records the last request for inspection.
seen <- new.env()
mock_api <- function(routes) {
  function(req) {
    seen$req <- req
    path <- sub("^https?://[^/]+/aef/?", "", req$url)
    path <- sub("\\?.*$", "", path)
    key <- paste(req$method %||% "GET", path)
    hit <- routes[[key]]
    if (is.null(hit)) return(httr2::response_json(status_code = 404L, body = list(error = list(code = "not_found", message = "No such endpoint."))))
    httr2::response_json(status_code = hit$status %||% 200L, body = hit$body)
  }
}
`%||%` <- function(x, y) if (is.null(x)) y else x

envelope <- function(data, as_of = "2027-02-09", set = "P1-baseline") {
  list(as_of = as_of, parameter_set_id = set, data = data)
}
