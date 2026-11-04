#' Connection settings
#'
#' `set_token()` stores your team's token so that you never have to put it
#' in code. Like tidyfinance's `set_wrds_credentials()`, it asks for the
#' token, then whether to save it in this project's `.Renviron` or in the one
#' in your home folder, and offers to add a project `.Renviron` to
#' `.gitignore` so the token never ends up in Git. R reads `.Renviron` at
#' startup, so you run it once. In a script, pass the token instead (or set
#' the environment variable `AEF_TOKEN`): `set_token(token)` sets it for
#' the session without asking anything.
#'
#' `set_url()` points the client at another server, for example a test one.
#'
#' @param token Your team's token. Leave it out to be asked for it.
#' @param url Base address of the API.
#' @return Invisibly, the value set.
#' @export
set_token <- function(token = NULL) {
  ask <- is.null(token)
  if (ask) {
    if (!is_interactive()) api_error("missing_token", msg$token_noninteractive)
    token <- trimws(ask_line(msg$ask_token))
  }
  if (!is.character(token) || length(token) != 1L || !startsWith(token, "aef_")) {
    api_error("invalid_token", msg$token_invalid)
  }
  Sys.setenv(AEF_TOKEN = token)
  if (ask) store_token(token, ".Renviron")
  invisible(token)
}

#' @rdname set_token
#' @export
set_url <- function(url) {
  url <- sub("/+$", "", url)
  Sys.setenv(AEF_URL = url)
  invisible(url)
}

default_url <- "https://eumel.tail81c88a.ts.net/aef"

server_url <- function() sub("/+$", "", Sys.getenv("AEF_URL", default_url))

# One API call. GET requests are retried on rate limits and gateway errors;
# writes are not, so a submission is never sent twice. Statuses in `ok`
# return the parsed body; anything else becomes an aefsim_error.
api_call <- function(method, path, body = NULL, query = list(), ok = 200L) {
  token <- Sys.getenv("AEF_TOKEN")
  if (!nzchar(token)) api_error("missing_token", msg$missing_token)
  url <- server_url()
  req <- httr2::request(url) |>
    httr2::req_url_path_append(path) |>
    httr2::req_method(method) |>
    httr2::req_auth_bearer_token(token) |>
    httr2::req_user_agent(paste0("aefsim R client ", utils::packageVersion("aefsim"))) |>
    httr2::req_timeout(60) |>
    httr2::req_error(is_error = function(resp) FALSE)
  query <- Filter(Negate(is.null), query)
  if (length(query)) req <- httr2::req_url_query(req, !!!query)
  if (method == "GET") {
    req <- httr2::req_retry(
      req, max_tries = 3,
      is_transient = function(resp) httr2::resp_status(resp) %in% c(429L, 502L, 503L, 504L),
      backoff = function(i) getOption("aefsim.retry_wait", 1) * 2^(i - 1)
    )
  }
  if (!is.null(body)) req <- httr2::req_body_json(req, body, auto_unbox = TRUE, digits = NA, null = "null")
  resp <- tryCatch(httr2::req_perform(req), httr2_failure = function(e) {
    why <- paste(conditionMessage(e), if (!is.null(e$parent)) conditionMessage(e$parent))
    if (grepl("timeout|timed out", why, ignore.case = TRUE)) {
      api_error("timeout", paste0(sprintf(msg$timeout, url), if (method != "GET") msg$timeout_write))
    }
    api_error("connection_failed", sprintf(msg$connection_failed, url))
  })
  status <- httr2::resp_status(resp)
  json <- tryCatch(httr2::resp_body_json(resp, simplifyVector = FALSE), error = function(e) NULL)
  if (!status %in% ok) {
    err <- if (is.list(json)) json$error
    if (is.null(err$code)) {
      if (status %in% c(502L, 503L, 504L)) api_error("server_unavailable", sprintf(msg$server_unavailable, url, status), status)
      api_error("http_error", sprintf(msg$http_error, url, status), status)
    }
    message <- err$message %||% ""
    if (err$code %in% c("missing_token", "unknown_token")) message <- paste0(message, sprintf(msg$which_server, url))
    api_error(err$code, message, status)
  }
  json
}

# Errors carry the API's `code` and HTTP `status` (NA for problems the
# client catches before sending anything).
api_error <- function(code, message, status = NA_integer_) {
  stop(structure(
    class = c("aefsim_error", "error", "condition"),
    list(message = paste0(message, " [", code, "]"), call = NULL, code = code, status = status)
  ))
}

`%||%` <- function(x, y) if (is.null(x)) y else x
