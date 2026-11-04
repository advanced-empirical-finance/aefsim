# aefsim (Python)

Client for the trading simulation in Advanced Empirical Finance. Same functions, column names and messages as the R package; tables come back as polars DataFrames, like tidyfinance. See the [repository README](https://github.com/advanced-empirical-finance/aefsim) for the overview.

```sh
uv add "git+https://github.com/advanced-empirical-finance/aefsim#subdirectory=python"
```

```python
import aefsim                      # reads your token from AEF_TOKEN
import polars as pl
universe = aefsim.get_universe()
weights = pl.DataFrame({"ticker": ["AAPL", "MSFT"], "weight": [0.2, 0.2]})
check = aefsim.validate(weights, close_date=universe["close_date"].max())
print(check)
```
