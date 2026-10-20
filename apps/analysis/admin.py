"""
Django admin configuration for the analysis app.
"""

from django.contrib import admin

from .models import Analysis, AnalysisResult, Preset


@admin.register(Preset)
class PresetAdmin(admin.ModelAdmin):
    list_display = ("slug", "name")
    ordering = ("slug",)


@admin.register(Analysis)
class AnalysisAdmin(admin.ModelAdmin):
    list_display = ("slug", "input_hash_short", "engine_version", "created_at")
    ordering = ("-created_at",)
    readonly_fields = ("id", "slug", "input_hash", "created_at")

    @admin.display(description="Input hash")
    def input_hash_short(self, obj):
        return obj.input_hash[:12] + "…"



# Composite-key rows remain accessible through the ORM and securities summaries.
# Django 5.2 admin does not support composite primary keys.
