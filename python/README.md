# aefsim (Python)

Client for the trading simulation in Advanced Empirical Finance. Same functions as the R package; see the [repository README](https://github.com/advanced-empirical-finance/aefsim) for the overview.

```sh
pip install "git+https://github.com/advanced-empirical-finance/aefsim#subdirectory=python"
```

```python
import aefsim                      # reads your token from AEF_TOKEN
universe = aefsim.get_universe()
check = aefsim.validate({"AAPL": 0.2, "MSFT": 0.2}, as_of=universe.attrs["as_of"])
print(check)
```
