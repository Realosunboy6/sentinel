"""
Analysis models: Analysis, AnalysisResult, Preset.

Schema mirrors sentinel-schema.sql exactly:
  - analyses has NO auto-increment identity column; slug is the share token
  - Results cache keyed (input_hash, data_asof) — never mutated
"""

import uuid

from django.db import models


class Analysis(models.Model):
    """
    Represents a submitted portfolio analysis.  `slug` is a short base62
    token used in share URLs (/a/<slug>).  No identity/sequence column.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.TextField(unique=True)
    input_hash = models.TextField(db_index=True)
    inputs = models.JSONField()
    engine_version = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "analyses"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Analysis {self.slug}"


class AnalysisResult(models.Model):
    """
    Cached result for (input_hash, data_asof).  Pure function: same inputs +
    same data vintage → same result.  Old rows are never mutated.
    """

    input_hash = models.TextField()
    data_asof = models.DateField()
    metrics = models.JSONField()
    computed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("input_hash", "data_asof")]
        ordering = ["-computed_at"]

    def __str__(self):
        return f"Result {self.input_hash[:8]} asof {self.data_asof}"


class Preset(models.Model):
    """
    Named preset portfolios (e.g. '60-40', 'k5-sample').  Seeded via
    management command; editable through the admin.
    """

    slug = models.TextField(primary_key=True)
    name = models.TextField()
    inputs = models.JSONField()

    class Meta:
        ordering = ["slug"]

    def __str__(self):
        return self.name
