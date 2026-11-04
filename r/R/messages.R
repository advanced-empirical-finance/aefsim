# Messages the client writes itself, word for word the same as in the Python
# package (python/src/aefsim/client.py); only the example differs. Errors
# from the server arrive with their own message.
msg <- list(
  missing_token = "No team token. Set the environment variable AEF_TOKEN to your team's token (see the aefsim README), or call set_token().",
  connection_failed = "Could not reach the simulation server at %s. Check your internet connection and try again; if it stays unreachable, tell the course team.",
  timeout = "The simulation server at %s did not answer within 60 seconds. Try again in a few minutes.",
  timeout_write = " Your submission may have arrived anyway: check get_submissions() before you submit again.",
  server_unavailable = "The simulation server at %s is not responding (HTTP %d). It may be restarting: try again in a few minutes, and tell the course team if it stays down.",
  http_error = "Unexpected answer from the simulation server at %s (HTTP %d).",
  which_server = " (server: %s)",
  close_date_missing = "Give close_date: the date of the close your decision is based on, such as \"2027-03-01\".",
  date_invalid = "%s must be a date in the form YYYY-MM-DD, such as \"2027-03-01\", not \"%s\".",
  weights_columns = "weights needs the columns ticker and weight, such as %s.",
  weights_tickers = "Every weight needs a ticker, such as %s.",
  weights_numbers = "Each weight must be one finite number; check %s.",
  weights_duplicates = "Each ticker may appear only once in weights; check %s.",
  submission_id = "Give submission_id: the id submit() returned, or one from get_submissions().",
  rejected = "Submission %s was rejected and will not trade:"
)

weights_example <- 'tibble::tibble(ticker = "AAPL", weight = 0.1)'
