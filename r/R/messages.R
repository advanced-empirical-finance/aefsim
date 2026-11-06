# Messages the client writes itself, word for word the same as in the Python
# package (python/src/aefsim/client.py); only the example differs. Errors
# from the server arrive with their own message.
msg <- list(
  missing_token = "No team token. Run set_token() once to save it, or set the environment variable AEF_TOKEN.",
  token_noninteractive = "set_token() asks for your token, which needs an interactive session. In a script, use set_token(\"aef_...\") or set the environment variable AEF_TOKEN.",
  token_invalid = "That is not a trading game token: team tokens start with aef_.",
  ask_token = "Paste your team's token (it starts with aef_): ",
  ask_where = "Where do you want to save it? Enter 'project' for %s in this project's folder or 'home' for your home folder: ",
  ask_replace = "%s already holds a token. Do you want to replace it? Enter 'yes' or 'no': ",
  ask_gitignore = "Do you want to add %s to .gitignore, so your token never ends up in Git? It is highly recommended! Enter 'yes' or 'no': ",
  gitignore_added = "%s added to .gitignore.",
  gitignore_not_added = "%s NOT added to .gitignore.",
  token_saved = "Your token is saved in %s and set for this session.",
  token_not_saved = "Not saved: the token is set for this session only. Run set_token() again to save it.",
  connection_failed = "Could not reach the trading game's server at %s. Check your internet connection and try again; if it stays unreachable, tell the course team.",
  timeout = "The trading game's server at %s did not answer within 60 seconds. Try again in a few minutes.",
  timeout_write = " Your submission may have arrived anyway: check get_submissions() before you submit again.",
  server_unavailable = "The trading game's server at %s is not responding (HTTP %d). It may be restarting: try again in a few minutes, and tell the course team if it stays down.",
  http_error = "Unexpected answer from the trading game's server at %s (HTTP %d).",
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
