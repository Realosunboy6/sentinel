# Sentinel

Open-source portfolio analytics web app — optimization, backtesting and risk monitoring (Portfolio Visualizer-class), powered by the [portlab](https://github.com/Realosunboy6/portlab) engine. Built with Django 5.

---

## Prerequisites

| Tool | Version |
|---|---|
| Python | 3.12+ |
| PostgreSQL | 15+ (or Docker) |
| pip | latest |

---

## Local development setup

### 1. Clone and install dependencies

```bash
git clone <repo-url>
cd sentinel
pip install -r requirements.txt
```

### 2. Configure the environment

```bash
cp .env.example .env
# Edit .env and set SECRET_KEY to a long random string.
# DATABASE_URL defaults to the Docker Compose Postgres — change if needed.
```

### 3. Start PostgreSQL

With Docker (recommended):

```bash
docker compose up -d
```

Or point `DATABASE_URL` at an existing PostgreSQL 15+ instance.

For local testing without PostgreSQL:

```bash
# SQLite — fine for unit tests, not for production
export DATABASE_URL=sqlite:///./sentinel-dev.db
```

### 4. Apply migrations

```bash
python manage.py migrate
```

### 5. Create a superuser (for the admin)

```bash
python manage.py createsuperuser
```

### 6. Seed presets

```bash
python manage.py seed_presets
```

### 7. Seed market data (12-ticker universe)

This hits Yahoo Finance — requires a network connection.

```bash
python manage.py refresh_prices --symbols SPY QQQ BND AAPL MSFT IWM GLD MCK LLY PWR NVDA STX
```

### 8. Start the dev server

```bash
python manage.py runserver
```

Visit:
- **http://localhost:8000/securities/** — M0 gate page (price counts + latest dates)
- **http://localhost:8000/admin/** — Django admin (securities, presets, analyses)

---

## Running the test suite

```bash
# Set a DATABASE_URL (SQLite works for the full unit + smoke-test suite):
export DATABASE_URL=sqlite:///./sentinel-test.db
export SECRET_KEY=dev-only-secret

pytest
```

Expected: **23 tests, all green**.

---

## Nightly price refresh (cron)

```bash
# Add to crontab — runs at 01:00 UTC every weekday:
0 1 * * 1-5 cd /path/to/sentinel && python manage.py refresh_prices >> /var/log/sentinel-refresh.log 2>&1
```

A failed refresh does **not** take the site down — the previous cache continues
serving, and the vintage label on every results page shows the stale date.

---

## Repository layout

```
sentinel/
  SENTINEL-BUILD-SPEC.md        ← full build brief
  m0-scaffold-plan.md           ← M0 implementation plan
  manage.py
  requirements.txt
  docker-compose.yml
  .env.example
  sentinel/                     ← project package (settings, urls, wsgi)
  apps/
    core/                       ← securities-list page, base templates
    marketdata/                 ← Security/PriceHistory models, ingestion, sources
    analysis/                   ← Analysis/Preset models, engine adapter (M1+)
    tools/                      ← 18 tool pages (M4)
  templates/                    ← base.html + per-app templates
  static/                       ← styles.css, echarts.min.js (M1)
  docs/design/                  ← design package (mockups, schema, snippets)
  scripts/                      ← nightly job wrapper (M5)
  tests/
```

---

## Milestones

| # | Gate |
|---|---|
| **M0** ✅ | `pytest` green; securities list page works |
| M1 | Analyzer core + golden-number tests |
| M2 | RiskLens + VaR backtests |
| M3 | Optimizer |
| M4 | All 19 tool pages |
| M5 | Hardening + deploy |

---

## Commit authorship

All commits in this repo are authored:

```
Ibrahim Oyeyinka <ibrahimoyeyinka@yahoo.com>
```
