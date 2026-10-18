"""
Custom template filters for Sentinel.

Usage in templates:
    {% load sentinel_filters %}
    {{ value|pct:1 }}    → "16.5%"   (value is a fraction like 0.1646)
    {{ value|pct:2 }}    → "16.46%"
    {{ value|dollar:0 }} → "$24,324"
"""

from django import template

register = template.Library()


@register.filter
def pct(value, decimal_places=1):
    """Multiply by 100 and format as a percentage string (no % symbol)."""
    try:
        return f"{float(value) * 100:.{int(decimal_places)}f}"
    except (TypeError, ValueError):
        return "—"


@register.filter
def dollar(value, decimal_places=0):
    """Format a float as a dollar value with commas."""
    try:
        return f"{float(value):,.{int(decimal_places)}f}"
    except (TypeError, ValueError):
        return "—"


@register.filter
def pct_sign(value, decimal_places=2):
    """Like pct but prefixes '+' for positives."""
    try:
        v = float(value) * 100
        sign = "+" if v >= 0 else ""
        return f"{sign}{v:.{int(decimal_places)}f}"
    except (TypeError, ValueError):
        return "—"
