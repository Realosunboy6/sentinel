# Sentinel

Open-source portfolio analytics web app — optimization, backtesting and risk monitoring (Portfolio Visualizer-class), powered by the [portlab](https://github.com/Realosunboy6/portlab) engine. Built with Django 5.2 (composite primary keys).

---

## Prerequisites

| Tool | Version |
|---|---|
| Python | 3.12 (verified); 3.14 also tested |
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
# Edit .env: set SECRET_KEY and POSTGRES_PASSWORD.
# Set the same password in DATABASE_URL; URL-encode special characters.
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
- **http://localhost:8000/analyze** — portfolio analyzer; open Risk from a completed analysis
- **http://localhost:8000/optimize** — optimize the selected analysis
- **http://localhost:8000/tools/risk-parity** — compare risk contributions
- **http://localhost:8000/tools/rolling-optimization** — dated rolling target allocations

---

## Running the test suite

```bash
# Set a DATABASE_URL (SQLite works for the full unit + smoke-test suite):
export DATABASE_URL=sqlite:///./sentinel-test.db
export SECRET_KEY=dev-only-secret

pytest
```

M0–M3 baseline: **167 tests passed on PostgreSQL**. M4 adds fixture-backed tool coverage; on SQLite, the production row-lock test is skipped. See the current [M4 gate record](m4-tools-plan.md) for validation status.

PowerShell equivalent:

```powershell
$env:DATABASE_URL = 'sqlite:///:memory:'
$env:SECRET_KEY = 'dev-only-secret'
python -m pytest
```

---

## Nightly price refresh (cron)

```bash
# Add to crontab — runs at 01:00 UTC every weekday:
0 1 * * 1-5 cd /path/to/sentinel && python manage.py refresh_prices >> /var/log/sentinel-refresh.log 2>&1
```

A failed refresh does **not** take the site down — the previous cache continues
serving, and the vintage label on every results page shows the stale date.

---

## Production container and release procedure

The repository includes a Linux container running gunicorn with WhiteNoise
static assets. PostgreSQL remains a separate persistent service. Before a
release, set a long random `SECRET_KEY`, `POSTGRES_PASSWORD`, the public
`ALLOWED_HOSTS`, and the full HTTPS origin in `CSRF_TRUSTED_ORIGINS`.

For local container verification:

```bash
export SECRET_KEY='replace-with-at-least-50-random-characters'
export POSTGRES_PASSWORD='replace-with-a-database-password'
docker compose build
docker compose up -d db
docker compose run --rm web python manage.py migrate
docker compose run --rm web python manage.py seed_presets
docker compose up -d web
curl --fail http://localhost:8000/healthz
```

For an HTTPS deployment, also set:

```bash
export ALLOWED_HOSTS='sentinel.example.com'
export CSRF_TRUSTED_ORIGINS='https://sentinel.example.com'
export SESSION_COOKIE_SECURE=True
export CSRF_COOKIE_SECURE=True
export SECURE_SSL_REDIRECT=True
export SECURE_HSTS_SECONDS=31536000
```

Run migrations as an explicit release step before switching traffic. The
rollback point is the previous container image; do not reverse a migration
until its data effect has been reviewed. Database backup and restore commands
depend on the selected host and must be recorded in the M5 gate report.

The weekday refresh command remains:

```bash
python manage.py refresh_prices
```

Schedule it for `01:00 UTC` and retain stdout/stderr with the platform logs.
Per-symbol failures return a nonzero exit status but do not remove the prior
cache. Inspect application errors by the 12-character reference shown to the
visitor.

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
    tools/                      ← 19-card gallery and tool pages (M4)
  templates/                    ← base.html + per-app templates
  static/                       ← styles.css, echarts.min.js (M1)
  docs/design/                  ← design package (mockups, schema, snippets)
  scripts/                      ← nightly wrapper and PostgreSQL schema verifier
  tests/
```

---

## Milestones

| # | Gate |
|---|---|
| **M0** Local repair gate | Corrected ingestion/actions/schema; see repair acceptance report |
| **M1** Local repair gate | Corrected Analyzer/cache/JSON API/charts; goldens unchanged |
| **M2** Local repair gate | RiskLens + web anchors + shared editor + ES99 |
| **M3** Ready for review | Optimizer/risk-parity/rolling; shared data fixes; 167 tests pass |
| **M4** Local implementation; gate open | All 19 cards and 15 new reports; PostgreSQL and mobile screenshot checks pending |
| **M5** In progress | Local hardening/container artifact complete; PostgreSQL, host deployment and walkthrough open |

M2 validation and calculation conventions: [gate report](docs/m2-gate.md).
M3 validation and calculation conventions: [gate report](docs/m3-gate.md).
Current repair evidence and remaining limits: [repair acceptance](docs/repair-acceptance.md).
Earlier findings: [build-contract review](docs/build-contract-audit.md), [outline review](docs/plan-outline-review.md).

---

## Commit authorship

All commits in this repo are authored:

```
Ibrahim Oyeyinka <ibrahimoyeyinka@yahoo.com>
```

## Corrected data and cache behavior

Requests use cached prices only. Unknown symbols show an inline instruction to
refresh history; they are not downloaded during a request. The refresh command
processes all tracked symbols plus `--symbols`, reconciles maximum available
adjusted history and upserts splits/dividends atomically. Corrected prices expire
derived results while retaining share links and their inputs. Cache hits also
verify the actual loaded price fingerprint, preventing same-date stale results.

Stale or unavailable holdings are explicitly listed before results, and remaining
weights are renormalized. Long interior gaps block the analysis rather than being
compressed into misleading daily returns. A stale benchmark blocks the request.
For an intentionally historical dataset, choose an end date within its history.

`POST /api/analyze` accepts JSON with `holdings` (weights in **percent**, as in the
form), `benchmark`, `start_date`, and `end_date`; it returns metrics, chart payloads
and a share URL. Standard Django CSRF protection applies. For example:

```json
{"holdings":[{"symbol":"SPY","weight":100}],"benchmark":"SPY","start_date":"2021-01-04","end_date":"2026-10-16"}
```

After applying migrations to an isolated PostgreSQL verification database,
`python scripts/verify_postgres_schema.py` compares all six business tables with
the locked SQL in a temporary reference schema. Original migrations are preserved;
the new upgrade migrations retain existing prices, actions, presets and slugs.
Back up an existing database before applying schema changes outside a test copy.

## Accounts and administration

Visitors never sign up or log in, and no visitor identity or portfolio-ownership
models exist. Per the owner's 2026-10-19 clarification, Django's staff-only admin
and its framework authentication tables remain for securities/preset curation.
