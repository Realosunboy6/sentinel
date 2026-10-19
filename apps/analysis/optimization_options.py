"""Shared optimizer choices and defaults; no engine imports."""

METHODS = {
    "max_sharpe": "Max Sharpe",
    "gmv": "Global minimum variance",
    "risk_parity": "Risk parity",
    "min_cvar": "Minimum CVaR (95%)",
    "black_litterman": "Black-Litterman",
    "turnover_aware": "Turnover-aware mean-variance",
}
ROLLING_METHODS = {k: METHODS[k] for k in ("gmv", "max_sharpe", "risk_parity", "turnover_aware")}
MIN_OBSERVATIONS = 60
