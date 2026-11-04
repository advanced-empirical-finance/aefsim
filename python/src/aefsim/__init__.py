"""Client for the trading simulation in Advanced Empirical Finance.

Start with ``set_token()`` or the environment variable ``AEF_TOKEN``.
"""

from .client import (
    VERSION as __version__,
    AefsimError,
    Check,
    cancel,
    get_benchmarks,
    get_calendar,
    get_leaderboard,
    get_parameters,
    get_performance,
    get_portfolio,
    get_submissions,
    get_universe,
    set_token,
    set_url,
    submit,
    validate,
)

__all__ = [
    "AefsimError", "Check", "cancel", "get_benchmarks", "get_calendar", "get_leaderboard",
    "get_parameters", "get_performance", "get_portfolio", "get_submissions", "get_universe",
    "set_token", "set_url", "submit", "validate",
]
