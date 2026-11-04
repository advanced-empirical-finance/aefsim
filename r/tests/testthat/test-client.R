# The same nine scenarios as python/tests/test_client.py.

test_that("the universe is typed and carries its as_of", {
  httr2::local_mocked_responses(mock_api(list("GET universe" = list(body = envelope(list(
    list(ticker = "AAPL", name = "Apple", exchange = "Nasdaq", eligible = TRUE, sp500 = TRUE, delisted_on = NULL),
    list(ticker = "PENNY", name = "Penny", exchange = "NYSE", eligible = FALSE, sp500 = FALSE, delisted_on = NULL)
  ))))))
  u <- get_universe()
  expect_equal(u$ticker, c("AAPL", "PENNY"))
  expect_type(u$eligible, "logical")
  expect_s3_class(u$delisted_on, "Date")
  expect_equal(u$as_of, as.Date(c("2027-02-09", "2027-02-09")))
  expect_true("Authorization" %in% names(seen$req$headers))
  expect_false(grepl("?", seen$req$url, fixed = TRUE))
})

test_that("the calendar and the rules mark what comes next", {
  httr2::local_mocked_responses(mock_api(list(
    "GET calendar" = list(body = envelope(list(next_fill = "2027-02-10", next_deadline = "2027-02-10T14:00:00Z", fills = list(
      list(date = "2027-02-09", deadline = "2027-02-09T14:00:00Z"),
      list(date = "2027-02-10", deadline = "2027-02-10T14:00:00Z")
    )))),
    "GET parameters" = list(body = envelope(list(next_fill = "2027-02-10", sets = list(
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

test_that("validate sends as_of and weights and returns a check", {
  httr2::local_mocked_responses(mock_api(list("POST validate" = list(body = envelope(check_ok)))))
  x <- validate(c(AAPL = 0.3), as_of = as.Date("2027-02-09"))
  expect_equal(seen$req$body$data$as_of, "2027-02-09")
  expect_equal(seen$req$body$data$weights, list(AAPL = 0.3))
  expect_true(x$ok)
  expect_equal(x$fill_date, as.Date("2027-02-10"))
  expect_output(print(x), "OK")
})

test_that("weights come as vectors, lists or data frames; bad input fails early", {
  httr2::local_mocked_responses(mock_api(list("POST validate" = list(body = envelope(check_ok)))))
  validate(data.frame(ticker = c("AAPL", "MSFT"), weight = c(0.2, 0.1)), as_of = "2027-02-09")
  expect_equal(seen$req$body$data$weights, list(AAPL = 0.2, MSFT = 0.1))
  validate(list(AAPL = 0.25), as_of = "2027-02-09")
  expect_equal(seen$req$body$data$weights, list(AAPL = 0.25))
  validate(numeric(0), as_of = "2027-02-09")
  expect_length(seen$req$body$data$weights, 0)
  expect_error(validate(c(AAPL = NA), as_of = "2027-02-09"), "finite")
  expect_error(validate(c(0.2), as_of = "2027-02-09"), "ticker names")
  expect_error(validate(c(AAPL = 0.1)), "as_of")
})

test_that("a rejected submission is returned with a warning, not an error", {
  httr2::local_mocked_responses(mock_api(list("POST submit" = list(status = 422L, body = envelope(check_bad)))))
  expect_warning(x <- submit(c(PENNY = 0.3), as_of = "2027-02-09", rationale = "test"), "ineligible_ticker")
  expect_false(x$ok)
  expect_equal(x$status, "rejected")
  expect_equal(x$errors$ticker, "PENNY")
  expect_equal(seen$req$body$data$rationale, "test")
  expect_output(print(x), "ineligible_ticker PENNY")
})

test_that("API errors carry their code and status; a missing token fails early", {
  httr2::local_mocked_responses(mock_api(list("GET portfolio" = list(
    status = 401L, body = list(error = list(code = "unauthorized", message = "Send your team token."))
  ))))
  err <- tryCatch(get_portfolio(), aefsim_error = function(e) e)
  expect_equal(err$code, "unauthorized")
  expect_equal(err$status, 401L)
  withr::local_envvar(AEF_TOKEN = "")
  expect_error(get_portfolio(), "No token")
})

test_that("lookups retry on busy servers, writes never do", {
  # httr2's mocking bypasses its retry loop, so check the retry policy each
  # request carries; the Python test counts the calls themselves.
  httr2::local_mocked_responses(mock_api(list(
    "GET leaderboard" = list(status = 503L, body = list(error = list(code = "not_ready", message = "Later."))),
    "POST submit" = list(status = 502L, body = list(error = list(code = "bad_gateway", message = "Down.")))
  )))
  expect_error(get_leaderboard(), class = "aefsim_error")
  policy <- seen$req$policies
  expect_equal(policy$retry_max_tries, 3)
  expect_true(policy$retry_is_transient(httr2::response(status_code = 503L)))
  expect_false(policy$retry_is_transient(httr2::response(status_code = 422L)))
  expect_error(submit(numeric(0), as_of = "2027-02-09", rationale = "x"), class = "aefsim_error")
  expect_null(seen$req$policies$retry_max_tries)
})

test_that("submissions keep their weights per row", {
  httr2::local_mocked_responses(mock_api(list("GET submissions" = list(body = envelope(list(
    list(submission_id = "a", submitted_at = "2027-02-09T13:00:00Z", as_of = "2027-02-08", fill_date = "2027-02-09",
         status = "accepted", error_code = NULL, cancelled = FALSE, filled = TRUE, rationale = "x", weights = list(AAPL = 0.5, MSFT = 0.5)),
    list(submission_id = "b", submitted_at = "2027-02-08T13:00:00Z", as_of = "2027-02-05", fill_date = "2027-02-08",
         status = "accepted", error_code = NULL, cancelled = TRUE, filled = FALSE, rationale = "y", weights = list())
  ))))))
  x <- get_submissions()
  expect_equal(x$weights[[1]], c(AAPL = 0.5, MSFT = 0.5))
  expect_length(x$weights[[2]], 0)
  expect_equal(format(x$submitted_at[1], tz = "UTC"), "2027-02-09 13:00:00")
  expect_equal(x$cancelled, c(FALSE, TRUE))
})

test_that("cancel, portfolio, performance, leaderboard and benchmarks parse", {
  httr2::local_mocked_responses(mock_api(list(
    "DELETE submit/a" = list(body = envelope(list(submission_id = "a", cancelled_at = "2027-02-09T12:00:00Z", fill_date = "2027-02-09"))),
    "GET portfolio" = list(body = envelope(list(date = "2027-02-09", nav = 1e6, cash = 2e5, positions = list(
      list(ticker = "AAPL", shares = 100, price = 200, value = 2e4, weight = 0.02, stale = FALSE)
    )))),
    "GET performance" = list(body = envelope(list(
      summary = list(list(team_id = "team-01", sharpe = 0.5)),
      benchmarks = list(list(pseudonym = "Market", sharpe = 0.4)),
      series = list(list(date = "2027-02-09", nav_net = 1e6))
    ))),
    "GET leaderboard" = list(body = envelope(list(
      list(pseudonym = "marmot", you = TRUE, rank = 1L, sharpe = 0.5),
      list(pseudonym = "Market", you = FALSE, rank = NULL, sharpe = 0.4)
    ))),
    "GET benchmarks" = list(body = envelope(list(
      summary = list(list(pseudonym = "Market", sharpe = 0.4)),
      series = list(list(pseudonym = "Market", team_id = "bot-market", date = "2027-02-09", nav_net = 1e6))
    )))
  )))
  expect_equal(cancel("a")$fill_date, as.Date("2027-02-09"))
  p <- get_portfolio()
  expect_equal(p$date, as.Date("2027-02-09"))
  expect_equal(p$positions$ticker, "AAPL")
  expect_equal(get_performance()$series$date, as.Date("2027-02-09"))
  lb <- get_leaderboard()
  expect_equal(lb$you, c(TRUE, FALSE))
  expect_equal(lb$rank, c(1L, NA))
  expect_equal(get_benchmarks()$series$date, as.Date("2027-02-09"))
})
