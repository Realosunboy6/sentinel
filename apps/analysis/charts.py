"""
Chart payload serializers — converts engine output to §9-envelope dicts.

Spec §9 envelope:
    {"chart": "<type>", "title": ..., "series": [...], "meta": {"asof": ...}}

Every chart includes:
- Hover tooltip with exact values
- Data-vintage label in meta
- Axis labels

These dicts are serialised to JSON and embedded in the template; ECharts
reads them directly via JSON.parse().
"""

from __future__ import annotations

import math
from typing import Any


def _asof_label(asof: str) -> str:
    return f"Data as of {asof}"


# ---------------------------------------------------------------------------
# Growth line chart
# ---------------------------------------------------------------------------

def growth_chart(
    dates: list[str],
    portfolio_values: list[float],
    benchmark_values: list[float],
    asof: str,
) -> dict[str, Any]:
    return {
        "chart": "line",
        "title": "Portfolio Growth ($10,000)",
        "xAxis": {"data": dates, "type": "category"},
        "yAxis": {"type": "value", "name": "Value ($)", "nameLocation": "middle", "nameGap": 60},
        "legend": {"data": ["Portfolio", "Benchmark"]},
        "tooltip": {
            "trigger": "axis",
            "formatter": "{b}<br/>{a0}: ${c0}<br/>{a1}: ${c1}",
        },
        "series": [
            {
                "name": "Portfolio",
                "type": "line",
                "data": [round(v, 2) for v in portfolio_values],
                "smooth": False,
                "showSymbol": False,
                "lineStyle": {"color": "#10233f", "width": 2},
            },
            {
                "name": "Benchmark",
                "type": "line",
                "data": [round(v, 2) for v in benchmark_values],
                "smooth": False,
                "showSymbol": False,
                "lineStyle": {"color": "#94a3b8", "width": 1.5, "type": "dashed"},
            },
        ],
        "meta": {"asof": asof, "label": _asof_label(asof)},
    }


# ---------------------------------------------------------------------------
# Drawdown area chart
# ---------------------------------------------------------------------------

def drawdown_chart(
    dates: list[str],
    drawdown_pct: list[float],
    asof: str,
) -> dict[str, Any]:
    return {
        "chart": "line",
        "title": "Drawdown",
        "xAxis": {"data": dates, "type": "category"},
        "yAxis": {
            "type": "value",
            "name": "Drawdown (%)",
            "nameLocation": "middle",
            "nameGap": 60,
            "axisLabel": {"formatter": "{value}%"},
        },
        "tooltip": {
            "trigger": "axis",
            "formatter": "{b}<br/>Drawdown: {c}%",
        },
        "series": [
            {
                "name": "Drawdown",
                "type": "line",
                "data": [round(v * 100, 4) for v in drawdown_pct],
                "areaStyle": {"color": "rgba(220,38,38,0.15)"},
                "lineStyle": {"color": "#dc2626", "width": 1.5},
                "showSymbol": False,
            }
        ],
        "meta": {"asof": asof, "label": _asof_label(asof)},
    }


# ---------------------------------------------------------------------------
# Annual returns bar chart
# ---------------------------------------------------------------------------

def annual_bars_chart(
    years: list[str],
    returns: list[float],
    asof: str,
) -> dict[str, Any]:
    colors = ["#0e9f6e" if r >= 0 else "#dc2626" for r in returns]
    return {
        "chart": "bar",
        "title": "Annual Returns",
        "xAxis": {"data": years, "type": "category"},
        "yAxis": {
            "type": "value",
            "axisLabel": {"formatter": "{value}%"},
        },
        "tooltip": {
            "trigger": "axis",
            "formatter": "{b}: {c}%",
        },
        "series": [
            {
                "name": "Annual Return",
                "type": "bar",
                "data": [
                    {"value": round(r * 100, 2), "itemStyle": {"color": c}}
                    for r, c in zip(returns, colors)
                ],
            }
        ],
        "meta": {"asof": asof, "label": _asof_label(asof)},
    }


# ---------------------------------------------------------------------------
# Monthly heatmap
# ---------------------------------------------------------------------------

_MONTH_LABELS = ["Jan","Feb","Mar","Apr","May","Jun",
                 "Jul","Aug","Sep","Oct","Nov","Dec"]


def monthly_heatmap_chart(
    monthly_rows: list[dict],
    asof: str,
) -> dict[str, Any]:
    """
    monthly_rows: [{"year": 2021, "month": 1, "value": 0.038}, ...]
    """
    years = sorted(set(r["year"] for r in monthly_rows))
    # Build data as [month_idx, year_idx, value*100]
    year_index = {y: i for i, y in enumerate(years)}
    data = [
        [r["month"] - 1, year_index[r["year"]], round(r["value"] * 100, 2)]
        for r in monthly_rows
    ]
    return {
        "chart": "heatmap",
        "title": "Monthly Returns (%)",
        "xAxis": {"data": _MONTH_LABELS, "type": "category"},
        "yAxis": {"data": [str(y) for y in years], "type": "category"},
        "visualMap": {
            "min": -15,
            "max": 15,
            "calculable": True,
            "inRange": {"color": ["#dc2626", "#ffffff", "#0e9f6e"]},
        },
        "tooltip": {
            "trigger": "item",
            "formatter": "{b} {a}: {c}%",
        },
        "series": [
            {
                "name": "Return",
                "type": "heatmap",
                "data": data,
                "label": {"show": True, "formatter": "{c}%", "fontSize": 11},
            }
        ],
        "meta": {"asof": asof, "label": _asof_label(asof)},
    }


# ---------------------------------------------------------------------------
# Allocation donut
# ---------------------------------------------------------------------------

def allocation_donut_chart(
    symbols: list[str],
    weights: list[float],
    asof: str,
) -> dict[str, Any]:
    return {
        "chart": "pie",
        "title": "Allocation",
        "tooltip": {
            "trigger": "item",
            "formatter": "{b}: {d}%",
        },
        "legend": {"orient": "vertical", "left": "left"},
        "series": [
            {
                "name": "Weight",
                "type": "pie",
                "radius": ["40%", "70%"],
                "data": [
                    {"name": s, "value": round(w * 100, 2)}
                    for s, w in zip(symbols, weights)
                ],
                "label": {"formatter": "{b}\n{d}%"},
            }
        ],
        "meta": {"asof": asof, "label": _asof_label(asof)},
    }


# ---------------------------------------------------------------------------
# Correlation heatmap
# ---------------------------------------------------------------------------

def correlation_heatmap_chart(
    labels: list[str],
    matrix: list[list[float]],
    asof: str,
) -> dict[str, Any]:
    n = len(labels)
    data = [
        [j, i, matrix[i][j]]
        for i in range(n)
        for j in range(n)
    ]
    return {
        "chart": "heatmap",
        "title": "Correlation Matrix",
        "xAxis": {"data": labels, "type": "category", "axisLabel": {"rotate": 30}},
        "yAxis": {"data": labels, "type": "category"},
        "visualMap": {
            "min": -1,
            "max": 1,
            "calculable": True,
            "inRange": {"color": ["#dc2626", "#ffffff", "#0e9f6e"]},
        },
        "tooltip": {
            "trigger": "item",
            "formatter": "{a} / {b}: {c}",
        },
        "series": [
            {
                "name": "Correlation",
                "type": "heatmap",
                "data": [[d[0], d[1], round(d[2], 4)] for d in data],
                "label": {
                    "show": True,
                    "formatter": "{c}",
                    "fontSize": 11,
                },
            }
        ],
        "meta": {"asof": asof, "label": _asof_label(asof)},
    }


# ---------------------------------------------------------------------------
# Efficient frontier + portfolio dot
# ---------------------------------------------------------------------------

def frontier_chart(
    risk_return_points: list[dict],
    portfolio_point: dict,
    asof: str,
) -> dict[str, Any]:
    frontier_data = [
        [round(p["risk"] * 100, 4), round(p["return"] * 100, 4)]
        for p in risk_return_points
    ]
    port_data = [
        [round(portfolio_point["risk"] * 100, 4), round(portfolio_point["return"] * 100, 4)]
    ]
    return {
        "chart": "scatter",
        "title": "Efficient Frontier",
        "xAxis": {
            "type": "value",
            "name": "Volatility (%)",
            "nameLocation": "middle",
            "nameGap": 35,
        },
        "yAxis": {
            "type": "value",
            "name": "Return (%)",
            "nameLocation": "middle",
            "nameGap": 50,
        },
        "tooltip": {
            "trigger": "item",
            "formatter": "Vol: {c[0]}%  Ret: {c[1]}%",
        },
        "series": [
            {
                "name": "Frontier",
                "type": "line",
                "data": frontier_data,
                "showSymbol": False,
                "lineStyle": {"color": "#10233f"},
            },
            {
                "name": "Your portfolio",
                "type": "scatter",
                "data": port_data,
                "symbolSize": 14,
                "itemStyle": {"color": "#0e9f6e"},
                "label": {
                    "show": True,
                    "formatter": "Your portfolio",
                    "position": "right",
                },
            },
        ],
        "meta": {"asof": asof, "label": _asof_label(asof)},
    }


# ---------------------------------------------------------------------------
# Helper: build all chart payloads from the engine metrics dict
# ---------------------------------------------------------------------------

def build_all_charts(metrics: dict, asof: str) -> dict[str, Any]:
    """
    Convenience wrapper: convert a full engine metrics dict into a dict of
    chart payloads keyed by name.
    """
    growth = metrics.get("growth", {})
    dates = growth.get("dates", [])
    port_values = growth.get("portfolio", [])
    bench_values = growth.get("benchmark", [])

    dd = metrics.get("drawdown", {})
    dd_dates = dd.get("dates", [])
    dd_values = dd.get("values", [])

    annual = metrics.get("annual", {})
    years = sorted(annual.keys())
    annual_returns = [annual[y] for y in years]

    corr = metrics.get("correlation", {})
    frontier = metrics.get("frontier", {})

    holdings_symbols = list((metrics.get("per_asset") or {}).keys())
    portfolio_meta = metrics.get("portfolio", {})

    # Weights for the donut — stored in frontier portfolio dot if present
    # Fall back to equal weight for display if not provided.
    return {
        "growth": growth_chart(dates, port_values, bench_values, asof),
        "drawdown": drawdown_chart(dd_dates, dd_values, asof),
        "annual": annual_bars_chart(years, annual_returns, asof),
        "monthly": monthly_heatmap_chart(metrics.get("monthly", []), asof),
        "correlation": correlation_heatmap_chart(
            corr.get("labels", []), corr.get("matrix", []), asof
        ),
        "frontier": frontier_chart(
            frontier.get("points", []),
            frontier.get("portfolio", {"risk": 0, "return": 0}),
            asof,
        ),
    }
