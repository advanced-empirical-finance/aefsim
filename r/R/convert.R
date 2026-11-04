date_cols <- c("date", "close_date", "trade_date", "effective_from", "delisted_on", "start", "end", "next_trade_date")
time_cols <- c("submitted_at", "deadline", "cancelled_at", "next_deadline", "time")

# JSON records (a list of objects) to a tibble. Scalar fields become
# vectors, NULL becomes NA, anything nested a list column; known date and
# time fields get their types.
as_tbl <- function(records, lists = character()) {
  if (!length(records)) return(tibble::tibble())
  cols <- unique(unlist(lapply(records, names)))
  out <- lapply(stats::setNames(cols, cols), function(col) {
    v <- lapply(records, function(r) r[[col]])
    if (col %in% lists) return(v)
    nested <- vapply(v, function(e) (is.list(e) && length(e) > 0L) || length(e) > 1L, logical(1))
    if (any(nested)) return(v)
    unlist(lapply(v, function(e) if (!length(e)) NA else e))
  })
  typed(tibble::as_tibble(out))
}

typed <- function(x) {
  for (col in intersect(names(x), date_cols)) x[[col]] <- as.Date(unlist_na(x[[col]]))
  for (col in intersect(names(x), time_cols)) x[[col]] <- parse_time(unlist_na(x[[col]]))
  x
}

unlist_na <- function(x) if (is.list(x)) vapply(x, function(e) if (!length(e)) NA_character_ else as.character(e)[1], character(1)) else x

parse_time <- function(x) as.POSIXct(x, format = "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")

as_date1 <- function(x) if (is.null(x)) as.Date(NA) else as.Date(x)

# A JSON object of tickers and weights to a tibble of `ticker` and `weight`.
weights_tbl <- function(w) {
  w <- unlist(w)
  tibble::tibble(ticker = names(w) %||% character(0), weight = unname(as.numeric(w %||% numeric(0))))
}

# Weights from a data frame with ticker and weight columns, a named vector or
# a named list, as a JSON-ready named list.
weights_body <- function(weights) {
  if (is.data.frame(weights)) {
    if (!all(c("ticker", "weight") %in% names(weights))) bad_weights("weights_columns")
    tickers <- as.character(weights$ticker)
    values <- as.list(weights$weight)
  } else if (is.atomic(weights) || is.list(weights)) {
    if (is.null(weights)) bad_weights("weights_columns")
    tickers <- names(weights) %||% rep(NA_character_, length(weights))
    values <- as.list(unname(weights))
  } else {
    bad_weights("weights_columns")
  }
  if (!length(values)) return(stats::setNames(list(), character(0)))
  if (anyNA(tickers) || any(!nzchar(trimws(tickers)))) bad_weights("weights_tickers")
  finite <- vapply(values, function(v) is.numeric(v) && length(v) == 1L && is.finite(v), logical(1))
  if (!all(finite)) api_error("malformed_weights", sprintf(msg$weights_numbers, paste(tickers[!finite], collapse = ", ")))
  key <- toupper(trimws(tickers))
  if (anyDuplicated(key)) api_error("duplicate_ticker", sprintf(msg$weights_duplicates, paste(unique(key[duplicated(key)]), collapse = ", ")))
  stats::setNames(lapply(values, as.numeric), tickers)
}

bad_weights <- function(which) api_error("malformed_weights", sprintf(msg[[which]], weights_example))

# A date argument as "YYYY-MM-DD"; Date, POSIXct or such a string.
date_string <- function(x, name, code = "invalid_date") {
  ok <- length(x) == 1L && (inherits(x, c("Date", "POSIXt")) || is.character(x))
  d <- if (ok) tryCatch(as.Date(x, optional = TRUE), error = function(e) as.Date(NA)) else as.Date(NA)
  if (!ok || is.na(d) || (is.character(x) && !grepl("^\\d{4}-\\d{2}-\\d{2}", x))) {
    api_error(code, sprintf(msg$date_invalid, name, paste(format(x), collapse = " ")))
  }
  format(d)
}

close_date_string <- function(close_date) {
  if (is.null(close_date)) api_error("invalid_close_date", msg$close_date_missing)
  date_string(close_date, "close_date", "invalid_close_date")
}
