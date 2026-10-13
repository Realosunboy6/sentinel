# Sentinel — visual spec for the build

Mockup: `index.html`, `dashboard.html` (Analyzer), `risk.html`, shared `styles.css`.
Every chart in the mockup is inline SVG generated from one consistent sample dataset —
in production each is rendered from live engine output. Numbers in the mockup are real
(computed from the sample series), not lorem ipsum.

## Design language

- **Standard professional fintech.** Navy `#10233f` chrome, white cards on `#f6f8fb`,
  emerald `#0e9f6e` accent/positive, red `#dc2626` negative, amber warnings.
- System font stack; tabular numerals everywhere money appears.
- Cards: 10px radius, 1px `#e2e8f0` border, soft shadow. No gradients except the hero.
- Responsive: grids collapse to one column under 860px; nav links hide (hamburger TBD).

## Chart inventory (what PV does well, adopted)

| Visual | Page | Production behavior |
|---|---|---|
| Portfolio growth line (portfolio vs benchmark) | Landing hero card, Analyzer | Hover crosshair + values; linear/log toggle |
| Drawdown area chart | Analyzer, Risk | Red area, deepest point annotated |
| Annual returns bars | Analyzer | Green/red bars, value labels |
| Monthly returns heatmap | Analyzer | Year × month grid, green→red scale, annual column |
| Efficient frontier + "your portfolio" dot | Analyzer | Curve from the engine's frontier; dot = entered weights |
| Allocation donut | Analyzer | Conic segments, legend with weights |
| Correlation matrix heatmap | Analyzer | Blue (positive) scale, values in cells |
| Daily-return histogram + VaR line | Risk | Worst-5% bars red; dashed VaR marker |
| Performance summary table | Analyzer | PV layout: Portfolio vs Benchmark columns |
| Basel traffic light | Risk | Green/amber/red dot + label |
| Regime badge | Analyzer, Risk | CALM (emerald) / STRESSED (red) pill |

## Interaction notes for the real build

- Charts are the product: every chart gets a hover tooltip and an axis; static images are not acceptable.
- Heatmap cells show the value on hover with the exact period return.
- All result sections share one data vintage label ("history Jan 2021 – Oct 2026").
- Empty/short-history states are designed, not improvised: show the panel with a
  one-line explanation (see RiskLens young-history handling in portlab).

## Tool → visualization matrix (every tool, no exceptions)

Checked against PV's published tool inventory (2026-10-12). Rule: **no tool ships
without at least one signature visual.** Mockups: `dashboard.html`, `risk.html`,
`optimize.html`, and the `tools.html` gallery (one card per tool).

| Tool | Signature visual | PV has it? |
|---|---|---|
| Backtest | Growth line + drawdown + monthly heatmap | Yes |
| RiskLens report | Return histogram with VaR line, traffic light | No — ours |
| Optimization (MVO/CVaR/robust) | Efficient frontier + portfolio dot | Yes |
| Monte Carlo | Percentile fan chart | Yes |
| Financial goals | Projection fan vs goal line | Yes |
| Factor analysis | Diverging factor-exposure bars | Yes |
| Tactical allocation | Price vs MA signal chart | Yes |
| Rolling optimization | Stacked rolling-weights area | Yes |
| Rolling metrics | Rolling Sharpe/vol lines | Yes |
| Asset–liability | Assets vs liabilities + funded ratio | No — ours |
| Options | Payoff diagram | No — ours |
| Technical analysis | Price + Bollinger bands (+ RSI/MACD panels) | No — ours |
| Forecast | Forecast fan ( widening cone ) | No — ours |
| Stress testing | Scenario P&L bars | No — ours |
| Attribution (Brinson) | Waterfall chart | No — ours |
| Risk parity | Risk-contribution bars | Yes |
| Tax-aware / tax-lot | After-tax vs pre-tax growth lines | No — ours |
| Correlations | Correlation heatmap matrix | Yes |
| Drawdown analysis | Drawdown area + episode table | Yes |

## What not to do

- No login, account, or brokerage-connect UI anywhere (architecture: weights-in only).
- No dark mode in v1. No stock-photo hero. No purple/blue gradient clichés beyond the navy hero.
