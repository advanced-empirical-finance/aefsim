# The dialogue behind set_token(), after tidyfinance::set_wrds_credentials():
# where to save the token, whether to replace one already there, and whether
# to add the file to .gitignore. Prompts and messages are the same as in the
# Python package, which saves to .env instead.
store_token <- function(token, file) {
  where <- tolower(trimws(ask_line(sprintf(msg$ask_where, file))))
  dir <- switch(where, project = getwd(), home = home_dir(), NULL)
  if (is.null(dir)) {
    say(msg$token_not_saved)
    return(invisible(FALSE))
  }
  path <- file.path(dir, file)
  lines <- if (file.exists(path)) readLines(path, warn = FALSE) else character()
  if (any(grepl("^AEF_TOKEN=", lines)) && !yes(ask_line(sprintf(msg$ask_replace, file)))) {
    say(msg$token_not_saved)
    return(invisible(FALSE))
  }
  writeLines(c(lines[!grepl("^AEF_TOKEN=", lines)], paste0("AEF_TOKEN=", token)), path)
  if (where == "project") ignore_file(dir, file)
  say(sprintf(msg$token_saved, path))
  invisible(TRUE)
}

ignore_file <- function(dir, file) {
  gitignore <- file.path(dir, ".gitignore")
  lines <- if (file.exists(gitignore)) readLines(gitignore, warn = FALSE) else character()
  if (file %in% trimws(lines) || paste0("/", file) %in% trimws(lines)) return(invisible(TRUE))
  if (yes(ask_line(sprintf(msg$ask_gitignore, file)))) {
    writeLines(c(lines, file), gitignore)
    say(sprintf(msg$gitignore_added, file))
  } else {
    say(sprintf(msg$gitignore_not_added, file))
  }
}

yes <- function(answer) tolower(trimws(answer)) %in% c("yes", "y")

# Seams for the tests.
ask_line <- function(prompt) readline(prompt)
is_interactive <- function() interactive()
home_dir <- function() path.expand("~")
say <- function(text) message(text)
