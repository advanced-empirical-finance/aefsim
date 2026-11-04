#' Validate, submit and cancel
#'
#' `validate()` runs every check the simulation would run and stores
#' nothing. `submit()` sends the weights for the next fill; the last
#' accepted submission before that fill's deadline (09:00 New York time) is
#' filled at the open, and a rejected one is kept in your log with its
#' error codes. `cancel()` withdraws a submission before its deadline.
#'
#' @param weights Target weights by ticker: a named numeric vector, or a
#'   data frame with columns `ticker` and `weight`. Tickers left out get
#'   weight zero; the rest of the book stays in cash.
#' @param as_of Date of the last close your decision used.
#' @param rationale Why you trade, for your decision log. Required by
#'   `submit()`.
#' @param submission_id Id returned by `submit()`.
#' @return An `aefsim_check`: a list with `ok`, `fill_date`,
#'   `parameter_set_id`, `weights`, `errors` (a tibble of `code`, `ticker`,
#'   `message`) and `diagnostics`; from `submit()` also `submission_id` and
#'   `status`. `cancel()` returns a list with `submission_id`,
#'   `cancelled_at` and `fill_date`.
#' @export
validate <- function(weights, as_of, rationale = NULL) {
  json <- api_call("POST", "validate", body = list(as_of = as_of_string(as_of), weights = weights_body(weights), rationale = rationale))
  as_check(json$data)
}

#' @rdname validate
#' @export
submit <- function(weights, as_of, rationale) {
  if (missing(rationale)) rationale <- NULL
  json <- api_call("POST", "submit", ok = c(201L, 422L),
                   body = list(as_of = as_of_string(as_of), weights = weights_body(weights), rationale = rationale))
  out <- as_check(json$data)
  if (!out$ok) warning("Submission rejected: ", paste(unique(out$errors$code), collapse = ", "), call. = FALSE)
  out
}

#' @rdname validate
#' @export
cancel <- function(submission_id) {
  json <- api_call("DELETE", paste0("submit/", submission_id))
  list(
    submission_id = json$data$submission_id,
    cancelled_at = parse_time(json$data$cancelled_at),
    fill_date = as_date1(json$data$fill_date)
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
      fill_date = as_date1(d$fill_date),
      parameter_set_id = d$parameter_set_id,
      weights = unlist(d$weights) %||% stats::setNames(numeric(0), character(0)),
      errors = errors,
      diagnostics = d$diagnostics
    ),
    class = "aefsim_check"
  )
}

#' @export
print.aefsim_check <- function(x, ...) {
  what <- if (is.null(x$status)) "Check" else paste0("Submission ", x$submission_id, " (", x$status, ")")
  cat(what, ": ", if (x$ok) "OK" else "problems found", "\n", sep = "")
  if (!is.na(x$fill_date)) cat("Fill date: ", format(x$fill_date), ", rules ", x$parameter_set_id %||% "?", "\n", sep = "")
  d <- x$diagnostics
  if (length(d)) {
    cat(sprintf("Positions %d, gross %.3f, net %.3f, cash %.3f\n", d$n_positions, d$gross, d$net, d$cash))
  }
  if (nrow(x$errors)) {
    cat("Errors:\n")
    for (i in seq_len(nrow(x$errors))) {
      tk <- if (is.na(x$errors$ticker[i])) "" else paste0(" ", x$errors$ticker[i])
      cat("  ", x$errors$code[i], tk, ": ", x$errors$message[i], "\n", sep = "")
    }
  }
  invisible(x)
}
