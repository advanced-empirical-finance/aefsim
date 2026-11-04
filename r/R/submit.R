#' Validate, submit and cancel
#'
#' `validate()` runs every check the simulation would run and stores
#' nothing. `submit()` sends target weights; they trade at the next market
#' open whose deadline (09:00 New York time) has not passed, so a
#' submission sent after a deadline, over a weekend or before the
#' simulation starts waits for the next open. The last accepted submission
#' before a deadline is the one that trades; a rejected one is kept in your
#' log with its errors. `cancel()` withdraws a submission before its
#' deadline.
#'
#' @param weights Target weights: a data frame with columns `ticker` and
#'   `weight`, such as `tibble::tibble(ticker = "AAPL", weight = 0.1)`. A
#'   named numeric vector works too. Stocks you leave out get weight zero;
#'   the rest of the book stays in cash.
#' @param close_date Date of the close your decision is based on, such as
#'   `"2027-03-01"`: usually `max(get_universe()$close_date)`.
#' @param rationale Why you chose these weights, for your decision log.
#'   Required by `submit()`.
#' @param submission_id Id returned by `submit()`.
#' @return An `aefsim_check`: a list with `ok`, `trade_date`,
#'   `parameter_set_id` (the rules for that trade), `weights` (a tibble of
#'   `ticker` and `weight`), `errors` (a tibble of `code`, `ticker`,
#'   `message`) and `diagnostics`; from `submit()` also `submission_id` and
#'   `status`. `cancel()` returns a list with `submission_id`,
#'   `cancelled_at` and `trade_date`.
#' @export
validate <- function(weights, close_date, rationale = NULL) {
  if (missing(close_date)) close_date <- NULL
  body <- list(close_date = close_date_string(close_date), weights = weights_body(weights), rationale = rationale)
  as_check(api_call("POST", "validate", body = body)$data)
}

#' @rdname validate
#' @export
submit <- function(weights, close_date, rationale) {
  if (missing(close_date)) close_date <- NULL
  if (missing(rationale)) rationale <- NULL
  body <- list(close_date = close_date_string(close_date), weights = weights_body(weights), rationale = rationale)
  out <- as_check(api_call("POST", "submit", ok = c(201L, 422L), body = body)$data)
  if (!out$ok) {
    warning(paste(c(sprintf(msg$rejected, out$submission_id), error_lines(out$errors)), collapse = "\n"), call. = FALSE)
  }
  out
}

#' @rdname validate
#' @export
cancel <- function(submission_id) {
  if (missing(submission_id) || !is.character(submission_id) || length(submission_id) != 1L || !nzchar(submission_id)) {
    api_error("invalid_submission_id", msg$submission_id)
  }
  json <- api_call("DELETE", paste0("submit/", submission_id))
  list(
    submission_id = json$data$submission_id,
    cancelled_at = parse_time(json$data$cancelled_at),
    trade_date = as_date1(json$data$trade_date)
  )
}

as_check <- function(d) {
  errors <- as_tbl(d$errors)
  if (!nrow(errors)) errors <- tibble::tibble(code = character(), ticker = character(), message = character())
  structure(
    list(
      ok = isTRUE(d$ok),
      submission_id = d$submission_id,
      status = d$status,
      trade_date = as_date1(d$trade_date),
      parameter_set_id = d$parameter_set_id,
      weights = weights_tbl(d$weights),
      errors = errors,
      diagnostics = d$diagnostics
    ),
    class = "aefsim_check"
  )
}

# "  ineligible_ticker PENNY: Not eligible on ..."
error_lines <- function(errors) {
  tk <- ifelse(is.na(errors$ticker), "", paste0(" ", errors$ticker))
  paste0("  ", errors$code, tk, ": ", errors$message)
}

#' @export
print.aefsim_check <- function(x, ...) {
  what <- if (is.null(x$status)) "Check" else paste0("Submission ", x$submission_id, " (", x$status, ")")
  cat(what, ": ", if (x$ok) "OK" else "problems found", "\n", sep = "")
  if (!is.na(x$trade_date)) {
    cat("Trades at the open on ", format(x$trade_date), " (rules ", x$parameter_set_id %||% "?", ")\n", sep = "")
  }
  d <- x$diagnostics
  if (length(d)) {
    cat(sprintf("Positions %d, gross %.3f, net %.3f, cash %.3f\n", d$n_positions, d$gross, d$net, d$cash))
  }
  if (nrow(x$errors)) cat("Errors:", error_lines(x$errors), sep = "\n")
  if (nrow(x$errors)) cat("\n")
  invisible(x)
}
