"""
Market data models: Security, PriceHistory, CorporateAction.

Schema mirrors sentinel-schema.sql exactly:
  - NUMERIC fields use DecimalField (never FloatField)
  - DATE fields use DateField
  - UUIDs as primary keys
"""

import uuid

from django.db import models
from apps.core.fields import FixedCharField


class Security(models.Model):
    ASSET_TYPE_CHOICES = [
        ("stock", "Stock"),
        ("etf", "ETF"),
        ("fund", "Fund"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    symbol = models.TextField()
    exchange = models.TextField(default="")
    name = models.TextField(null=True, blank=True)
    asset_type = models.TextField(default="stock", choices=ASSET_TYPE_CHOICES)
    currency = FixedCharField(max_length=3, default="USD")

    class Meta:
        db_table = "securities"
        verbose_name_plural = "securities"
        unique_together = [("symbol", "exchange")]
        ordering = ["symbol"]

    def __str__(self):
        return self.symbol


class PriceHistory(models.Model):
    """
    One row per (security, trading date), using the locked composite primary key.
    """

    pk = models.CompositePrimaryKey("security", "date")

    security = models.ForeignKey(
        Security, on_delete=models.CASCADE, related_name="pricehistory"
    )
    date = models.DateField()
    open = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    high = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    low = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    close = models.DecimalField(max_digits=18, decimal_places=4)
    adj_close = models.DecimalField(max_digits=18, decimal_places=4)
    volume = models.BigIntegerField(null=True, blank=True)

    class Meta:
        db_table = "price_history"
        ordering = ["security", "date"]

    def __str__(self):
        return f"{self.security.symbol} {self.date}"


class CorporateAction(models.Model):
    ACTION_TYPE_CHOICES = [
        ("SPLIT", "Split"),
        ("STOCK_DIVIDEND", "Stock Dividend"),
        ("CASH_DIVIDEND", "Cash Dividend"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    security = models.ForeignKey(
        Security, on_delete=models.CASCADE, related_name="corporate_actions"
    )
    ex_date = models.DateField()
    action_type = models.TextField(choices=ACTION_TYPE_CHOICES)
    ratio = models.DecimalField(max_digits=18, decimal_places=6)

    class Meta:
        db_table = "corporate_actions"
        constraints = [models.CheckConstraint(condition=models.Q(action_type__in=['SPLIT', 'STOCK_DIVIDEND', 'CASH_DIVIDEND']), name='corporate_actions_type_check')]
        unique_together = [("security", "ex_date", "action_type")]
        ordering = ["security", "ex_date"]

    def __str__(self):
        return f"{self.security.symbol} {self.action_type} {self.ex_date}"
