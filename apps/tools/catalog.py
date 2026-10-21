"""The locked §8 inventory, in the same order as the design gallery."""

TOOLS = [
    ("backtest", "Backtest", "backtest.svg", "Growth, drawdown and monthly returns", False),
    ("risk", "RiskLens report", "risk.svg", "Return losses and value at risk", True),
    ("optimize", "Optimization", "optimize.svg", "Frontier and your portfolio", False),
    ("monte-carlo", "Monte Carlo", "monte-carlo.svg", "Simulated portfolio outcomes", False),
    ("goals", "Financial goals", "goals.svg", "Projection range against a goal", False),
    ("factors", "Factor analysis", "factors.svg", "Return factor exposures", False),
    ("tactical", "Tactical allocation", "tactical.svg", "Trend signals and price", False),
    ("rolling-optimization", "Rolling optimization", "rolling-optimization.svg", "Weights through time", False),
    ("rolling-metrics", "Rolling metrics", "rolling-metrics.svg", "Sharpe and volatility through time", False),
    ("alm", "Asset-liability", "alm.svg", "Assets, liabilities and funding", True),
    ("options", "Options", "options.svg", "Payoff at expiry", True),
    ("technical", "Technical analysis", "technical.svg", "Price bands and momentum", True),
    ("forecast", "Forecast", "forecast.svg", "Projection and uncertainty", True),
    ("stress", "Stress testing", "stress.svg", "Scenario profit and loss", True),
    ("attribution", "Attribution", "attribution.svg", "Allocation and selection effects", True),
    ("risk-parity", "Risk parity", "risk-parity.svg", "Weight versus risk contribution", False),
    ("tax", "Tax-aware", "tax.svg", "Pre-tax and after-tax growth", True),
    ("correlations", "Correlations", "corr_heatmap.html", "Relationships among holdings", False),
    ("drawdowns", "Drawdown analysis", "drawdowns.svg", "Depth and recovery episodes", False),
]

PORTFOLIO_TOOLS = {"backtest", "monte-carlo", "goals", "factors", "tactical",
                   "rolling-metrics", "alm", "options", "technical", "forecast",
                   "stress", "attribution", "tax", "correlations", "drawdowns"}

PARAMETERS = {
    "backtest": [("rebalance", "Rebalance", "choice", "annually", ["monthly", "quarterly", "annually", "never"])],
    "rolling-metrics": [("window", "Trailing observations", "integer", 252, None)],
    "monte-carlo": [("initial", "Initial balance ($)", "number", 10000, None),
                    ("years", "Projection years", "integer", 10, None),
                    ("simulations", "Simulations", "integer", 1000, None),
                    ("contribution", "Annual contribution ($)", "number", 0, None)],
    "goals": [("initial", "Initial balance ($)", "number", 10000, None),
              ("target", "Goal ($)", "number", 20000, None),
              ("years", "Years to goal", "integer", 10, None),
              ("simulations", "Simulations", "integer", 1000, None),
              ("contribution", "Annual contribution ($)", "number", 0, None)],
    "tactical": [("window", "Moving average observations", "integer", 100, None)],
    "alm": [("initial", "Starting assets ($)", "number", 100000, None),
            ("payment", "Annual liability ($)", "number", 10000, None),
            ("years", "Liability years", "integer", 10, None),
            ("discount", "Annual discount rate (%)", "number", 3, None)],
    "options": [("strike", "Strike price ($; 0 = latest price)", "number", 0, None),
                ("expiry", "Years to expiry", "number", 1, None),
                ("volatility", "Implied volatility (%)", "number", 25, None),
                ("rate", "Risk-free rate (%)", "number", 3, None),
                ("market_premium", "Observed option premium ($; optional)", "number", 0, None),
                ("kind", "Option type", "choice", "call", ["call", "put"])],
    "forecast": [("steps", "Forecast trading days", "integer", 30, None)],
    "tax": [("initial", "Starting investment ($)", "number", 10000, None),
            ("short_rate", "Short-term gains tax (%)", "number", 30, None),
            ("long_rate", "Long-term gains tax (%)", "number", 15, None)],
}


def gallery_cards(slug=""):
    cards = []
    for code, name, preview, caption, beyond in TOOLS:
        route = "/risk" if code == "risk" else "/optimize" if code == "optimize" else f"/tools/{code}"
        cards.append({"code": code, "name": name, "preview": preview,
                      "caption": caption, "beyond": beyond,
                      "url": route + (f"?slug={slug}" if slug else "")})
    return cards
