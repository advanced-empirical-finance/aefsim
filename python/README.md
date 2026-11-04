# aefsim (Python)

Client for the trading simulation in Advanced Empirical Finance. Same functions and column names as the R package; tables come back as polars DataFrames, like tidyfinance. See the [repository README](https://github.com/advanced-empirical-finance/aefsim) for the overview.

```sh
pip install "git+https://github.com/advanced-empirical-finance/aefsim#subdirectory=python"
```

```python
import aefsim                      # reads your token from AEF_TOKEN
universe = aefsim.get_universe()
check = aefsim.validate({"AAPL": 0.2, "MSFT": 0.2}, as_of=universe["as_of"].max())
print(check)
```
