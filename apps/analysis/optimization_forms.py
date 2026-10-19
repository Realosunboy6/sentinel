"""Validated options shared by optimization and its two tool pages."""
import math

from django import forms

from .optimization_options import METHODS, ROLLING_METHODS


class OptimizationForm(forms.Form):
    method = forms.ChoiceField(choices=list(METHODS.items()), initial="max_sharpe")
    cap_percent = forms.DecimalField(label="Maximum weight per asset (%)", min_value=1, max_value=100, initial=50)
    rf_percent = forms.DecimalField(label="Annual risk-free rate (%)", min_value=-20, max_value=100, initial=0)
    tc_bps = forms.DecimalField(label="Cost per traded dollar (basis points)", min_value=0, max_value=1000, initial=10)
    views = forms.CharField(label="Black-Litterman return views", required=False,
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "MCK, 12, 60"}),
        help_text="One view per line: ticker, expected annual return %, confidence %. Example: MCK, 12, 60. Used only for Black-Litterman.")

    def __init__(self, *args, symbols=(), fixed_method=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.symbols = set(symbols)
        if fixed_method:
            self.fields["method"].choices = [(fixed_method, METHODS[fixed_method])]
            self.fields["method"].widget = forms.HiddenInput()
            self.fields.pop("views")

    def clean(self):
        data = super().clean()
        cap = data.get("cap_percent")
        if cap is not None and self.symbols and float(cap) * len(self.symbols) < 100 - 1e-8:
            self.add_error("cap_percent", f"With {len(self.symbols)} holdings, the cap must allow a total allocation of 100%.")
        data["parsed_views"] = []
        if data.get("method") != "black_litterman":
            return data
        seen = set()
        for number, line in enumerate(data.get("views", "").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                symbol, annual, confidence = [part.strip() for part in line.split(",")]
                symbol = symbol.upper()
                annual, confidence = float(annual), float(confidence)
                if symbol not in self.symbols or symbol in seen or not math.isfinite(annual) or annual <= -100 or not math.isfinite(confidence) or not 0 < confidence <= 100:
                    raise ValueError
            except ValueError:
                self.add_error("views", f"Line {number}: use a distinct portfolio ticker, return above -100%, and confidence above 0% up to 100%.")
                continue
            seen.add(symbol)
            data["parsed_views"].append({"symbol": symbol, "return": annual / 100, "confidence": confidence / 100})
        if not data["parsed_views"]:
            self.add_error("views", "Enter at least one explicit return view for Black-Litterman.")
        return data

    def engine_options(self):
        data = self.cleaned_data
        return {"method": data["method"], "max_weight": float(data["cap_percent"]) / 100,
                "rf": float(data["rf_percent"]) / 100, "tc_bps": float(data["tc_bps"]),
                "views": data["parsed_views"]}


class RollingOptimizationForm(OptimizationForm):
    lookback = forms.IntegerField(label="Prior trading observations", min_value=60, max_value=1260, initial=252)
    step = forms.IntegerField(label="Rebalance every (trading observations)", min_value=5, max_value=252, initial=21)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["method"].choices = list(ROLLING_METHODS.items())
        self.fields["method"].initial = "gmv"
        self.fields.pop("views")

    def engine_options(self):
        options = super().engine_options()
        options.pop("views")
        return {**options, "lookback": self.cleaned_data["lookback"], "step": self.cleaned_data["step"]}
