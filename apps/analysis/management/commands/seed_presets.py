"""
Management command: seed_presets

Inserts (or updates) the two required preset rows:
  - 60-40: SPY 60% / BND 40%
  - k5-sample: MCK/LLY/PWR/NVDA/STX at owner-confirmed weights

Safe to run multiple times (uses update_or_create).
"""

from django.core.management.base import BaseCommand

from apps.analysis.models import Preset

PRESETS = [
    {
        "slug": "60-40",
        "name": "60/40 Portfolio",
        "inputs": {
            "holdings": [
                {"symbol": "SPY", "weight": 0.60},
                {"symbol": "BND", "weight": 0.40},
            ],
            "settings": {"benchmark": "SPY"},
        },
    },
    {
        "slug": "k5-sample",
        "name": "K5 Sample",
        "inputs": {
            "holdings": [
                {"symbol": "MCK",  "weight": 0.2998},
                {"symbol": "LLY",  "weight": 0.2355},
                {"symbol": "PWR",  "weight": 0.1906},
                {"symbol": "NVDA", "weight": 0.1561},
                {"symbol": "STX",  "weight": 0.1180},
            ],
            "settings": {"benchmark": "SPY"},
        },
    },
]


class Command(BaseCommand):
    help = "Seed (or refresh) the two required preset portfolios."

    def handle(self, *args, **options):
        for preset in PRESETS:
            obj, created = Preset.objects.update_or_create(
                slug=preset["slug"],
                defaults={"name": preset["name"], "inputs": preset["inputs"]},
            )
            action = "Created" if created else "Updated"
            self.stdout.write(self.style.SUCCESS(f"  {action} preset: {preset['slug']}"))

        self.stdout.write(self.style.SUCCESS("Preset seeding complete."))
