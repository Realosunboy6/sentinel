"""
Django admin configuration for the marketdata app.
"""

from django.contrib import admin
from django.db.models import Count, Max

from .models import CorporateAction, PriceHistory, Security


@admin.register(Security)
class SecurityAdmin(admin.ModelAdmin):
    list_display = ("symbol", "exchange", "asset_type", "currency", "price_count", "latest_price_date")
    search_fields = ("symbol", "name")
    list_filter = ("asset_type", "currency")
    ordering = ("symbol",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(
            _price_count=Count("pricehistory"),
            _latest_date=Max("pricehistory__date"),
        )

    @admin.display(description="Price rows", ordering="_price_count")
    def price_count(self, obj):
        return obj._price_count

    @admin.display(description="Latest date", ordering="_latest_date")
    def latest_price_date(self, obj):
        return obj._latest_date


@admin.register(PriceHistory)
class PriceHistoryAdmin(admin.ModelAdmin):
    list_display = ("security", "date", "close", "adj_close", "volume")
    list_filter = ("security__symbol",)
    ordering = ("-date",)
    raw_id_fields = ("security",)


@admin.register(CorporateAction)
class CorporateActionAdmin(admin.ModelAdmin):
    list_display = ("security", "ex_date", "action_type", "ratio")
    list_filter = ("action_type",)
    ordering = ("-ex_date",)
    raw_id_fields = ("security",)
