date_cols <- c("date", "as_of", "fill_date", "effective_from", "delisted_on", "start", "end", "next_fill")
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

# Weights from a named vector, a named list or a data frame with ticker and
# weight columns, as a JSON-ready named list.
weights_body <- function(weights) {
  if (is.data.frame(weights)) {
    if (!all(c("ticker", "weight") %in% names(weights))) stop("A weights data frame needs columns `ticker` and `weight`.", call. = FALSE)
    weights <- stats::setNames(weights$weight, weights$ticker)
  }
  if (!length(weights)) return(stats::setNames(list(), character(0)))
  if (is.null(names(weights)) || any(!nzchar(names(weights)))) stop("Weights need ticker names.", call. = FALSE)
  w <- unlist(weights)
  if (!is.numeric(w) || any(!is.finite(w))) stop("Weights must be finite numbers.", call. = FALSE)
  as.list(w)
}

as_of_string <- function(as_of) {
  if (missing(as_of) || is.null(as_of)) stop("Give `as_of`: the date of the last close your decision used.", call. = FALSE)
  format(as.Date(as_of))
}
