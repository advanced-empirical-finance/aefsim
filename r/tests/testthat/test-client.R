# The same eleven scenarios as python/tests/test_client.py, with the same
# messages word for word.

test_that("the universe is typed and carries its close_date", {
  httr2::local_mocked_responses(mock_api(list("GET universe" = list(body = envelope(list(
    list(ticker = "AAPL", permno = 14593L, name = "Apple", exchange = "Nasdaq", sp500 = TRUE),
    list(ticker = "MSFT", permno = 10107L, name = "Microsoft", exchange = "Nasdaq", sp500 = TRUE)
  ))))))
  u <- get_universe()
  expect_equal(u$ticker, c("AAPL", "MSFT"))
  expect_identical(u$permno, c(14593L, 10107L))
  expect_type(u$sp500, "logical")
  expect_equal(u$close_date, as.Date(c("2027-02-09", "2027-02-09")))
  expect_true("Authorization" %in% names(seen$req$headers))
  expect_false(grepl("?", seen$req$url, fixed = TRUE))
  get_universe(close_date = as.Date("2027-02-05"))
  expect_match(seen$req$url, "close_date=2027-02-05", fixed = TRUE)
})

test_that("the calendar and the rules mark what comes next", {
  httr2::local_mocked_responses(mock_api(list(
    "GET calendar" = list(body = envelope(list(next_trade_date = "2027-02-10", next_deadline = "2027-02-10T14:00:00Z", trading_days = list(
      list(date = "2027-02-09", deadline = "2027-02-09T14:00:00Z"),
      list(date = "2027-02-10", deadline = "2027-02-10T14:00:00Z")
    )))),
    "GET parameters" = list(body = envelope(list(next_trade_date = "2027-02-10", sets = list(
      list(effective_from = "2027-02-08", set_id = "P1-baseline", cost_bps = 0),
      list(effective_from = "2027-03-01", set_id = "P2-costs", cost_bps = 10)
    ))))
  )))
  cal <- get_calendar()
  expect_equal(cal$is_next, c(FALSE, TRUE))
  expect_equal(format(cal$deadline[cal$is_next], tz = "UTC"), "2027-02-10 14:00:00")
  p <- get_parameters()
  expect_equal(p$applies_next, c(TRUE, FALSE))
  expect_s3_class(p$effective_from, "Date")
})

test_that("validate sends close_date and weights and returns a check", {
  httr2::local_mocked_responses(mock_api(list("POST validate" = list(body = envelope(check_ok)))))
  x <- validate(tibble::tibble(ticker = "AAPL", weight = 0.3), close_date = as.Date("2027-02-09"))
  expect_equal(seen$req$body$data$close_date, "2027-02-09")
  expect_equal(seen$req$body$data$weights, list(AAPL = 0.3))
  expect_true(x$ok)
  expect_equal(x$trade_date, as.Date("2027-02-10"))
  expect_equal(x$weights, tibble::tibble(ticker = "AAPL", weight = 0.3))
  expect_output(print(x), "Trades at the open on 2027-02-10 (rules P1-baseline)", fixed = TRUE)
})

test_that("weights come as data frames or named vectors; bad input fails early", {
  httr2::local_mocked_responses(mock_api(list("POST validate" = list(body = envelope(check_ok)))))
  validate(data.frame(ticker = c("AAPL", "MSFT"), weight = c(0.2, 0.1)), close_date = "2027-02-09")
  expect_equal(seen$req$body$data$weights, list(AAPL = 0.2, MSFT = 0.1))
  validate(c(AAPL = 0.25), close_date = "2027-02-09")
  expect_equal(seen$req$body$data$weights, list(AAPL = 0.25))
  validate(tibble::tibble(ticker = character(), weight = numeric()), close_date = "2027-02-09")
  expect_length(seen$req$body$data$weights, 0)
  example <- 'tibble::tibble(ticker = "AAPL", weight = 0.1)'
  fails <- function(expr) tryCatch({ expr; NULL }, aefsim_error = function(e) e)
  e <- fails(validate(tibble::tibble(ticker = "AAPL", weight = NA), close_date = "2027-02-09"))
  expect_equal(e$code, "malformed_weights")
  expect_equal(conditionMessage(e), "Each weight must be one finite number; check AAPL. [malformed_weights]")
  e <- fails(validate(c(0.2), close_date = "2027-02-09"))
  expect_equal(conditionMessage(e), paste0("Every weight needs a ticker, such as ", example, ". [malformed_weights]"))
  e <- fails(validate(tibble::tibble(symbol = "AAPL", w = 0.1), close_date = "2027-02-09"))
  expect_equal(conditionMessage(e), paste0("weights needs the columns ticker and weight, such as ", example, ". [malformed_weights]"))
  e <- fails(validate(tibble::tibble(ticker = c("AAPL", "aapl"), weight = 0.1), close_date = "2027-02-09"))
  expect_equal(conditionMessage(e), "Each ticker may appear only once in weights; check AAPL. [duplicate_ticker]")
  e <- fails(validate(c(AAPL = 0.1)))
  expect_equal(conditionMessage(e), 'Give close_date: the date of the close your decision is based on, such as "2027-03-01". [invalid_close_date]')
  e <- fails(validate(c(AAPL = 0.1), close_date = "03/01/2027"))
  expect_equal(conditionMessage(e), 'close_date must be a date in the form YYYY-MM-DD, such as "2027-03-01", not "03/01/2027". [invalid_close_date]')
  expect_true(is.na(e$status))
  expect_equal(seen$n, 3L)
})

test_that("a rejected submission is returned with a warning, not an error", {
  httr2::local_mocked_responses(mock_api(list("POST submit" = list(status = 422L, body = envelope(check_bad)))))
  w <- tryCatch(submit(c(PENNY = 0.3), close_date = "2027-02-09", rationale = "test"), warning = function(w) w)
  expect_equal(conditionMessage(w), "Submission team-01-x was rejected and will not trade:\n  ineligible_ticker PENNY: Not eligible on 2027-02-09.")
  x <- suppressWarnings(submit(c(PENNY = 0.3), close_date = "2027-02-09", rationale = "test"))
  expect_false(x$ok)
  expect_equal(x$status, "rejected")
  expect_equal(x$errors$ticker, "PENNY")
  expect_equal(seen$req$body$data$rationale, "test")
  expect_output(print(x), "ineligible_ticker PENNY")
})

test_that("API errors carry their code and status; a missing token fails early", {
  httr2::local_mocked_responses(mock_api(list("GET portfolio" = list(
    status = 401L, body = list(error = list(code = "unknown_token", message = "This server does not know your token."))
  ))))
  err <- tryCatch(get_portfolio(), aefsim_error = function(e) e)
  expect_equal(err$code, "unknown_token")
  expect_equal(err$status, 401L)
  expect_equal(conditionMessage(err), "This server does not know your token. (server: https://example.org/aef) [unknown_token]")
  withr::local_envvar(AEF_TOKEN = "")
  err <- tryCatch(get_portfolio(), aefsim_error = function(e) e)
  expect_equal(conditionMessage(err), "No team token. Run set_token() once to save it, or set the environment variable AEF_TOKEN. [missing_token]")
  withr::local_envvar(AEF_TOKEN = "aef_test")
  err <- tryCatch(cancel(""), aefsim_error = function(e) e)
  expect_equal(conditionMessage(err), "Give submission_id: the id submit() returned, or one from get_submissions(). [invalid_submission_id]")
})

test_that("lookups retry on busy servers, writes never do", {
  # httr2's mocking bypasses its retry loop, so check the retry policy each
  # request carries; the Python test counts the calls themselves.
  httr2::local_mocked_responses(mock_api(list(
    "GET leaderboard" = list(status = 503L, body = list(error = list(code = "not_ready", message = "Later."))),
    "POST submit" = list(status = 502L, raw = "<html>Bad gateway</html>")
  )))
  expect_error(get_leaderboard(), "Later. [not_ready]", fixed = TRUE)
  policy <- seen$req$policies
  expect_equal(policy$retry_max_tries, 3)
  expect_true(policy$retry_is_transient(httr2::response(status_code = 503L)))
  expect_false(policy$retry_is_transient(httr2::response(status_code = 422L)))
  err <- tryCatch(submit(numeric(0), close_date = "2027-02-09", rationale = "x"), aefsim_error = function(e) e)
  expect_equal(conditionMessage(err), paste(
    "The trading game's server at https://example.org/aef is not responding (HTTP 502).",
    "It may be restarting: try again in a few minutes, and tell the course team if it stays down. [server_unavailable]"
  ))
  expect_null(seen$req$policies$retry_max_tries)
})

test_that("submissions keep their weights per row", {
  httr2::local_mocked_responses(mock_api(list("GET submissions" = list(body = envelope(list(
    list(submission_id = "a", submitted_at = "2027-02-09T13:00:00Z", close_date = "2027-02-08", trade_date = "2027-02-09",
         status = "accepted", error_code = NULL, cancelled = FALSE, traded = TRUE, rationale = "x", weights = list(AAPL = 0.5, MSFT = 0.5)),
    list(submission_id = "b", submitted_at = "2027-02-08T13:00:00Z", close_date = "2027-02-05", trade_date = "2027-02-08",
         status = "accepted", error_code = NULL, cancelled = TRUE, traded = FALSE, rationale = "y", weights = list())
  ))))))
  x <- get_submissions()
  expect_equal(x$weights[[1]], tibble::tibble(ticker = c("AAPL", "MSFT"), weight = c(0.5, 0.5)))
  expect_equal(nrow(x$weights[[2]]), 0L)
  expect_equal(format(x$submitted_at[1], tz = "UTC"), "2027-02-09 13:00:00")
  expect_equal(x$trade_date, as.Date(c("2027-02-09", "2027-02-08")))
  expect_equal(x$cancelled, c(FALSE, TRUE))
})

test_that("cancel, portfolio, performance, leaderboard and benchmarks parse", {
  httr2::local_mocked_responses(mock_api(list(
    "DELETE submit/a" = list(body = envelope(list(submission_id = "a", cancelled_at = "2027-02-09T12:00:00Z", trade_date = "2027-02-09"))),
    "GET portfolio" = list(body = envelope(list(close_date = "2027-02-09", portfolio_value = 1e6, cash = 2e5, positions = list(
      list(ticker = "AAPL", shares = 100, price = 200, value = 2e4, weight = 0.02, stale = FALSE)
    )))),
    "GET performance" = list(body = envelope(list(
      summary = list(list(team_id = "team-01", sharpe = 0.5)),
      benchmarks = list(list(pseudonym = "Market", sharpe = 0.4)),
      series = list(list(date = "2027-02-09", portfolio_value = 1e6))
    ))),
    "GET leaderboard" = list(body = envelope(list(
      list(pseudonym = "marmot", you = TRUE, rank = 1L, sharpe = 0.5),
      list(pseudonym = "Market", you = FALSE, rank = NULL, sharpe = 0.4)
    ))),
    "GET benchmarks" = list(body = envelope(list(
      summary = list(list(pseudonym = "Market", sharpe = 0.4)),
      series = list(list(pseudonym = "Market", team_id = "bot-market", date = "2027-02-09", portfolio_value = 1e6))
    )))
  )))
  expect_equal(cancel("a")$trade_date, as.Date("2027-02-09"))
  p <- get_portfolio()
  expect_equal(nrow(p), 1L)
  expect_equal(p$close_date, as.Date("2027-02-09"))
  expect_equal(p$portfolio_value, 1e6)
  expect_equal(p$positions[[1]]$ticker, "AAPL")
  expect_equal(get_performance()$series$portfolio_value, 1e6)
  lb <- get_leaderboard()
  expect_equal(lb$you, c(TRUE, FALSE))
  expect_equal(lb$rank, c(1L, NA))
  expect_equal(get_benchmarks()$series$date, as.Date("2027-02-09"))
})

test_that("an unreachable server and unexpected answers get plain messages", {
  withr::local_envvar(AEF_URL = "http://127.0.0.1:9")
  err <- tryCatch(get_universe(), aefsim_error = function(e) e)
  expect_equal(conditionMessage(err), paste(
    "Could not reach the trading game's server at http://127.0.0.1:9. Check your internet connection and try again;",
    "if it stays unreachable, tell the course team. [connection_failed]"
  ))
  withr::local_envvar(AEF_URL = "https://example.org/aef")
  httr2::local_mocked_responses(mock_api(list("GET universe" = list(status = 418L, raw = "teapot"))))
  err <- tryCatch(get_universe(), aefsim_error = function(e) e)
  expect_equal(conditionMessage(err), "Unexpected answer from the trading game's server at https://example.org/aef (HTTP 418). [http_error]")
  expect_equal(err$status, 418L)
})

test_that("set_token() asks where to save the token and offers to add it to .gitignore", {
  project <- withr::local_tempdir()
  home <- withr::local_tempdir()
  withr::local_dir(project)
  withr::local_envvar(AEF_TOKEN = "")
  answers <- character()
  prompts <- character()
  said <- character()
  local_mocked_bindings(
    is_interactive = function() TRUE,
    ask_line = function(prompt) {
      prompts <<- c(prompts, prompt)
      a <- answers[1]
      answers <<- answers[-1]
      a
    },
    home_dir = function() home,
    say = function(text) said <<- c(said, text)
  )
  answers <- c(" aef_abc ", "project", "yes")
  set_token()
  expect_equal(Sys.getenv("AEF_TOKEN"), "aef_abc")
  expect_equal(readLines(file.path(project, ".Renviron")), "AEF_TOKEN=aef_abc")
  expect_equal(readLines(file.path(project, ".gitignore")), ".Renviron")
  expect_equal(prompts, c(
    "Paste your team's token (it starts with aef_): ",
    "Where do you want to save it? Enter 'project' for .Renviron in this project's folder or 'home' for your home folder: ",
    "Do you want to add .Renviron to .gitignore, so your token never ends up in Git? It is highly recommended! Enter 'yes' or 'no': "
  ))
  expect_equal(said, c(".Renviron added to .gitignore.",
                       paste0("Your token is saved in ", file.path(project, ".Renviron"), " and set for this session.")))

  writeLines(c("OTHER=1", "AEF_TOKEN=aef_old"), file.path(home, ".Renviron"))
  prompts <- character()
  answers <- c("aef_new", "home", "yes")
  set_token()
  expect_equal(readLines(file.path(home, ".Renviron")), c("OTHER=1", "AEF_TOKEN=aef_new"))
  expect_equal(prompts[3], ".Renviron already holds a token. Do you want to replace it? Enter 'yes' or 'no': ")

  said <- character()
  answers <- c("aef_session", "later")
  set_token()
  expect_equal(Sys.getenv("AEF_TOKEN"), "aef_session")
  expect_equal(said, "Not saved: the token is set for this session only. Run set_token() again to save it.")

  err <- tryCatch(set_token("nope"), aefsim_error = function(e) e)
  expect_equal(conditionMessage(err), "That is not a trading game token: team tokens start with aef_. [invalid_token]")
  local_mocked_bindings(is_interactive = function() FALSE)
  err <- tryCatch(set_token(), aefsim_error = function(e) e)
  expect_equal(conditionMessage(err), paste(
    "set_token() asks for your token, which needs an interactive session.",
    'In a script, use set_token("aef_...") or set the environment variable AEF_TOKEN. [missing_token]'
  ))
  set_token("aef_script")
  expect_equal(Sys.getenv("AEF_TOKEN"), "aef_script")
})
