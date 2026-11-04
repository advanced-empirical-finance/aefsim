universe <- envelope(list(
  list(ticker = "AAPL", name = "Apple", exchange = "Nasdaq", eligible = TRUE, sp500 = TRUE, delisted_on = NULL),
  list(ticker = "PENNY", name = "Penny", exchange = "NYSE", eligible = FALSE, sp500 = FALSE, delisted_on = NULL)
))
check_ok <- list(ok = TRUE, fill_date = "2027-02-10", parameter_set_id = "P1-baseline",
                 weights = list(AAPL = 0.3), errors = list(),
                 diagnostics = list(gross = 0.3, net = 0.3, cash = 0.7, n_positions = 1L, max_abs_weight = 0.3))
check_bad <- list(ok = FALSE, submission_id = "team-01-x", status = "rejected", fill_date = "2027-02-10",
                  parameter_set_id = "P1-baseline", weights = list(PENNY = 0.3),
                  errors = list(list(code = "ineligible_ticker", ticker = "PENNY", message = "Fails the filter.")),
                  diagnostics = list(gross = 0.3, net = 0.3, cash = 0.7, n_positions = 1L, max_abs_weight = 0.3))

test_that("the universe comes back as a typed tibble with its as_of", {
  httr2::local_mocked_responses(mock_api(list("GET universe" = list(body = universe))))
  u <- get_universe()
  expect_s3_class(u, "tbl_df")
  expect_equal(u$ticker, c("AAPL", "PENNY"))
  expect_type(u$eligible, "logical")
  expect_s3_class(u$delisted_on, "Date")
  expect_equal(attr(u, "as_of"), as.Date("2027-02-09"))
  expect_true("Authorization" %in% names(seen$req$headers))
})

test_that("validate sends as_of and weights and returns a check", {
  httr2::local_mocked_responses(mock_api(list("POST validate" = list(body = envelope(check_ok)))))
  x <- validate(c(AAPL = 0.3), as_of = as.Date("2027-02-09"))
  body <- seen$req$body$data
  expect_equal(body$as_of, "2027-02-09")
  expect_equal(body$weights, list(AAPL = 0.3))
  expect_true(x$ok)
  expect_equal(x$fill_date, as.Date("2027-02-10"))
  expect_equal(x$weights, c(AAPL = 0.3))
  expect_output(print(x), "OK")
})

test_that("weights can be a data frame, and empty weights mean all cash", {
  httr2::local_mocked_responses(mock_api(list("POST validate" = list(body = envelope(check_ok)))))
  validate(data.frame(ticker = c("AAPL", "MSFT"), weight = c(0.2, 0.1)), as_of = "2027-02-09")
  expect_equal(seen$req$body$data$weights, list(AAPL = 0.2, MSFT = 0.1))
  validate(numeric(0), as_of = "2027-02-09")
  expect_equal(length(seen$req$body$data$weights), 0)
  expect_error(validate(c(0.2), as_of = "2027-02-09"), "ticker names")
  expect_error(validate(c(AAPL = NA), as_of = "2027-02-09"), "finite")
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

test_that("API errors become aefsim_error conditions with the code", {
  httr2::local_mocked_responses(function(req) httr2::response_json(
    status_code = 401L, body = list(error = list(code = "unauthorized", message = "Send your team token."))
  ))
  err <- tryCatch(get_portfolio(), aefsim_error = function(e) e)
  expect_equal(err$code, "unauthorized")
  expect_equal(err$status, 401L)
  withr::local_envvar(AEF_TOKEN = "")
  expect_error(get_portfolio(), "No token")
})

test_that("submissions keep their weights as a list column", {
  subs <- envelope(list(
    list(submission_id = "a", submitted_at = "2027-02-09T13:00:00Z", as_of = "2027-02-08", fill_date = "2027-02-09",
         status = "accepted", error_code = NULL, cancelled = FALSE, filled = TRUE, rationale = "x", weights = list(AAPL = 0.5, MSFT = 0.5)),
    list(submission_id = "b", submitted_at = "2027-02-08T13:00:00Z", as_of = "2027-02-05", fill_date = "2027-02-08",
         status = "accepted", error_code = NULL, cancelled = TRUE, filled = FALSE, rationale = "y", weights = list())
  ))
  httr2::local_mocked_responses(mock_api(list("GET submissions" = list(body = subs))))
  x <- get_submissions()
  expect_equal(x$weights[[1]], c(AAPL = 0.5, MSFT = 0.5))
  expect_length(x$weights[[2]], 0)
  expect_s3_class(x$submitted_at, "POSIXct")
  expect_equal(format(x$submitted_at[1], tz = "UTC"), "2027-02-09 13:00:00")
})

test_that("cancel, portfolio, performance and leaderboard parse", {
  httr2::local_mocked_responses(mock_api(list(
    "DELETE submit/a" = list(body = envelope(list(submission_id = "a", cancelled_at = "2027-02-09T12:00:00Z", fill_date = "2027-02-09"))),
    "GET portfolio" = list(body = envelope(list(date = "2027-02-09", nav = 1e6, cash = 2e5, positions = list(
      list(ticker = "AAPL", shares = 100, price = 200, value = 2e4, weight = 0.02, stale = FALSE)
    )))),
    "GET performance" = list(body = envelope(list(summary = list(list(team_id = "team-01", sharpe = 0.5)),
                                                  benchmarks = list(list(pseudonym = "Market", sharpe = 0.4)),
                                                  series = list(list(date = "2027-02-09", nav_net = 1e6))))),
    "GET leaderboard" = list(body = envelope(list(list(pseudonym = "marmot", you = TRUE, rank = 1L, sharpe = 0.5))))
  )))
  expect_equal(cancel("a")$fill_date, as.Date("2027-02-09"))
  p <- get_portfolio()
  expect_equal(p$positions$ticker, "AAPL")
  expect_equal(get_performance()$series$date, as.Date("2027-02-09"))
  expect_true(get_leaderboard()$you)
})
