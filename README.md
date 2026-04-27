# Wolf15 SignalThrottle Service

![Status](https://img.shields.io/badge/status-MVP%20roadmap-blue)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-service-green)
![Railway](https://img.shields.io/badge/deploy-Railway-purple)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

**Wolf15 SignalThrottle Service** adalah microservice dashboard untuk membaca event `SignalThrottle` dari engine utama Wolf15, mengubah raw throttle logs menjadi **pressure block**, lalu menghasilkan **trade-plan JSON** berbasis kualitas logs, konteks OHLC, struktur market, dan fase pair.

Service ini **bukan order executor**.  
Service ini **tidak membuka posisi, tidak menutup posisi, dan tidak mengubah Layer-12 / risk engine / execution engine**.  
Fungsinya adalah menjadi **pressure intelligence layer** untuk owner/dashboard.

---

## Table of Contents

- [Overview](#overview)
- [Why This Service Exists](#why-this-service-exists)
- [Core Concept](#core-concept)
- [Architecture](#architecture)
- [Roadmap Phases](#roadmap-phases)
- [Repository Structure](#repository-structure)
- [Quick Start](#quick-start)
- [Railway Deployment](#railway-deployment)
- [Environment Variables](#environment-variables)
- [API Endpoints](#api-endpoints)
- [Dashboard](#dashboard)
- [Signal Rules](#signal-rules)
- [Market Context](#market-context)
- [Outcome Tracking](#outcome-tracking)
- [Engine Integration](#engine-integration)
- [Security Notes](#security-notes)
- [Testing](#testing)
- [License & Disclaimer](#license--disclaimer)

---

## Overview

`wolf15-signalthrottle-service` membaca event seperti:

```text
[SignalThrottle] USDJPY THROTTLED — 3 signals in last 300s (max 3)
```

Lalu service membentuk output seperti:

```json
{
  "symbol": "USDJPY",
  "signal_type": "SIGNAL_THROTTLE_PRESSURE",
  "pressure_grade": "A",
  "execution_grade": "A",
  "duration_minutes": 14.5,
  "event_count": 110,
  "density_per_minute": 7.59,
  "max_gap_seconds": 43.51,
  "chart_phase": "UPPER_RANGE_EXHAUSTION_RISK",
  "execution_side": "SELL_REJECTION_OR_EXIT_LONG",
  "entry_zone": "159.75-159.85",
  "invalidation": "160.05",
  "message": "USDJPY active pressure at upper resistance. Not a fresh buy. Protect long or sell rejection if price fails 159.85."
}
```

---

## Why This Service Exists

Dalam engine Wolf15, `SignalThrottle` berfungsi sebagai safety clamp ketika terlalu banyak EXECUTE verdict muncul pada symbol yang sama dalam window tertentu.

Namun raw throttle logs sendiri belum cukup untuk menentukan entry. Dari testing internal, korelasi terbaik adalah:

```text
SignalThrottle valid = pair sedang aktif
density = intensitas pressure
max_gap = kesehatan kontinuitas
block_relation = konteks lanjutan
OHLC = lokasi harga
chart_phase = arah dan fase market
execution_grade = layak/tidaknya output menjadi signal utama
```

Jadi service ini mengubah raw logs menjadi keputusan yang lebih dapat dibaca:

```text
logs → pressure block → OHLC context → phase classification → trade-plan JSON → dashboard
```

---

## Core Concept

### SignalThrottle is not direction

SignalThrottle hanya menunjukkan bahwa pair sedang aktif atau terlalu sering menghasilkan actionable signal dalam window tertentu.

Arah trade tetap ditentukan oleh:

- harga saat signal berakhir,
- struktur D1/H4/H1/M15,
- lokasi terhadap support/resistance,
- phase pair,
- density dan max gap,
- jarak antar-block logs.

### Pressure grade vs execution grade

Service ini memisahkan dua hal:

| Grade | Fungsi |
| --- | --- |
| `pressure_grade` | kualitas logs |
| `execution_grade` | kualitas eksekusi setelah chart dibaca |

Contoh:

```text
Pressure A+ + pivot reclaim      = buy continuation candidate
Pressure A+ + upper resistance   = exit long / sell rejection candidate
Pressure A+ + range middle       = wait
Pressure A + support decision    = conditional breakdown/reclaim
```

---

## Architecture

```text
wolf15-engine
    │
    │ structured SignalThrottle event
    ▼
POST /webhook/log
    │
    ▼
SignalThrottle Parser
    │
    ▼
Pressure Block Detector
    │
    ├─ duration_minutes
    ├─ event_count
    ├─ density_per_minute
    ├─ avg_gap_seconds
    └─ max_gap_seconds
    │
    ▼
Pressure Grader
    │
    ▼
OHLC Fetcher / Cache Reader
    │
    ├─ D1
    ├─ H4
    ├─ H1
    └─ M15
    │
    ▼
Market Phase Classifier
    │
    ▼
Trade Plan Builder
    │
    ▼
Postgres + Dashboard
    │
    ▼
Outcome Tracker
```

---

## Roadmap Phases

### Phase 1 — MVP Dashboard

Target:

```text
replay logs
parse SignalThrottle
detect pressure block
calculate metrics
grade pressure
show dashboard
```

Scope:

- FastAPI app
- dashboard HTML
- Postgres schema
- replay logs
- parser
- block detector
- pressure grading

Acceptance:

```text
/health OK
dashboard terbuka
raw logs bisa direplay
pressure block terbentuk
duration/event/density/max_gap benar
grade A/A+/B/C keluar
```

---

### Phase 2 — Market Context

Target:

```text
pressure block valid
→ fetch OHLC D1/H4/H1/M15
→ classify market phase
→ produce trade_plan JSON
```

Scope:

- Finnhub OHLC client
- D1/H4/H1/M15 fetch
- phase classifier
- trade_plan JSON

Acceptance:

```text
OHLC berhasil fetch
price_at_signal_end tersimpan
chart_phase keluar
trade_plan JSON tampil di dashboard
```

---

### Phase 3 — Realtime

Target:

```text
engine event
→ webhook/log
→ active block dashboard
→ soft/hard finalizer
```

Scope:

- `POST /webhook/log`
- soft finalizer
- hard finalizer
- active block dashboard

Finalizer rules:

```text
0s      event masuk → update active block
30s     no new event → COOLING
60–90s  no new event → SOFT_FINALIZE + build trade_plan JSON
300s    no new event → HARD_FINALIZE / archive
```

Acceptance:

```text
webhook menerima event
duplicate event diabaikan
active block update live
soft finalize otomatis
hard finalize otomatis
```

---

### Phase 4 — Outcome Tracking

Target:

```text
validate signal quality statistically
```

Scope:

- MFE/MAE 15/30/60
- signal result label
- performance by phase/grade

Outcome labels:

```text
FOLLOW_THROUGH_STRONG
FOLLOW_THROUGH_WEAK
NO_FOLLOW_THROUGH
REVERSAL_AGAINST_SIGNAL
CHOPPY_NO_EDGE
```

Acceptance:

```text
setiap trade_plan punya outcome 15/30/60 menit
dashboard menampilkan performance by phase/grade
export CSV/JSON tersedia
```

---

### Phase 5 — Engine Integration

Target:

```text
wolf15-engine emits structured SignalThrottle event
```

Scope:

- engine emits structured SignalThrottle event
- optional Redis/Postgres candle mirror
- webhook secret
- publisher timeout
- fallback safe behavior

Acceptance:

```text
engine publish event live
dashboard mati tidak mengganggu engine
event live muncul di dashboard
optional candle mirror siap
```

---

## Repository Structure

```text
wolf15-signalthrottle-service/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── logging_config.py
│   ├── lifecycle.py
│   │
│   ├── api/
│   │   ├── routes_health.py
│   │   ├── routes_webhook.py
│   │   ├── routes_replay.py
│   │   ├── routes_signals.py
│   │   ├── routes_blocks.py
│   │   ├── routes_market.py
│   │   └── routes_dashboard.py
│   │
│   ├── dashboard/
│   │   ├── view_models.py
│   │   ├── templates/
│   │   │   ├── base.html
│   │   │   ├── index.html
│   │   │   └── signal_detail.html
│   │   └── static/
│   │       ├── app.css
│   │       └── app.js
│   │
│   ├── ingestion/
│   │   ├── webhook_receiver.py
│   │   ├── replay_receiver.py
│   │   ├── log_normalizer.py
│   │   └── source_types.py
│   │
│   ├── parser/
│   │   ├── signalthrottle_parser.py
│   │   ├── symbol_normalizer.py
│   │   └── timestamp_mapper.py
│   │
│   ├── detector/
│   │   ├── sequence_builder.py
│   │   ├── block_detector.py
│   │   ├── block_relation.py
│   │   └── finalizer.py
│   │
│   ├── scoring/
│   │   ├── pressure_metrics.py
│   │   ├── pressure_grader.py
│   │   ├── execution_grader.py
│   │   └── final_score.py
│   │
│   ├── market/
│   │   ├── ohlc_provider_base.py
│   │   ├── finnhub_client.py
│   │   ├── ohlc_cache.py
│   │   ├── phase_classifier.py
│   │   ├── level_detector.py
│   │   └── market_snapshot_builder.py
│   │
│   ├── planner/
│   │   ├── trade_plan_builder.py
│   │   ├── action_mapper.py
│   │   ├── message_builder.py
│   │   └── risk_template.py
│   │
│   ├── storage/
│   │   ├── postgres.py
│   │   ├── repositories.py
│   │   ├── migrations.py
│   │   └── schema.sql
│   │
│   ├── outcomes/
│   │   ├── mfe_mae_tracker.py
│   │   ├── followthrough_tracker.py
│   │   └── outcome_classifier.py
│   │
│   └── models/
│       ├── log_event.py
│       ├── pressure_block.py
│       ├── market_snapshot.py
│       ├── trade_plan.py
│       └── dashboard.py
│
├── scripts/
│   ├── replay_logs.py
│   ├── seed_sample_data.py
│   ├── backfill_blocks.py
│   └── export_trade_plans.py
│
├── tests/
│   ├── test_signalthrottle_parser.py
│   ├── test_block_detector.py
│   ├── test_pressure_grader.py
│   ├── test_phase_classifier.py
│   ├── test_trade_plan_builder.py
│   └── fixtures/
│       ├── usdjpy_r7.log
│       ├── nzdchf_blocks.log
│       ├── cadchf_blocks.log
│       └── eurchf_blocks.log
│
├── docs/
│   ├── ARCHITECTURE.md
│   ├── RAILWAY_DEPLOY.md
│   ├── DASHBOARD_SPEC.md
│   ├── API_SPEC.md
│   └── SIGNAL_RULES.md
│
├── Dockerfile
├── railway.toml
├── requirements.txt
├── .env.example
├── README.md
└── CHANGELOG.md
```

---

## Quick Start

### 1. Clone repository

```bash
git clone git@github.com:tjx578/wolf15-signalthrottle-service.git
cd wolf15-signalthrottle-service
```

### 2. Create virtual environment

```bash
python -m venv .venv
source .venv/bin/activate
```

Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment

```bash
cp .env.example .env
```

Database note:

- This service targets PostgreSQL. The schema in `app/storage/schema.sql` uses PostgreSQL-specific types and DDL such as `BIGSERIAL`, `TIMESTAMPTZ`, `JSONB`, and `CREATE TABLE IF NOT EXISTS`.
- If you open the repo in VS Code with the MSSQL extension installed, workspace settings in `.vscode/settings.json` auto-disable the T-SQL language service for non-MSSQL files to avoid false syntax errors on the Postgres schema.

Edit `.env`:

```env
APP_ENV=development
DATABASE_URL=postgresql://user:password@localhost:5432/wolf15_signalthrottle
OHLC_PROVIDER=finnhub
FINNHUB_API_KEY=your_key
OWNER_TIMEZONE=Asia/Makassar
CHART_TIME_OFFSET_HOURS=3
```

### 5. Run database migration

```bash
python -m app.storage.migrations
```

### 6. Run local server

```bash
uvicorn app.main:app --reload --port 8000
```

Open dashboard:

```text
http://localhost:8000/
```

---

## Railway Deployment

### Required services

```text
Railway Project: wolf15-production
├── wolf15-engine
├── wolf15-signalthrottle-service
├── PostgreSQL
└── Redis optional
```

### Deploy steps

```bash
git add .
git commit -m "init signalthrottle dashboard service"
git push origin main
```

In Railway:

```text
1. New Service
2. Deploy from GitHub repo
3. Select wolf15-signalthrottle-service
4. Add PostgreSQL
5. Add environment variables
6. Deploy
7. Open /health
8. Open /
```

### Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY scripts ./scripts

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
```

### railway.toml

```toml
[build]
builder = "DOCKERFILE"

[deploy]
restartPolicyType = "ON_FAILURE"
restartPolicyMaxRetries = 10

[variables]
APP_ENV = "production"
SERVICE_NAME = "wolf15-signalthrottle-service"
```

---

## Environment Variables

| Variable | Required | Default | Purpose |
| --- | ---: | --- | --- |
| `APP_ENV` | no | `production` | App environment |
| `SERVICE_NAME` | no | `wolf15-signalthrottle-service` | Service name |
| `DATABASE_URL` | yes | - | PostgreSQL connection |
| `LOG_TIMEZONE` | no | `UTC` | Engine log timezone |
| `OWNER_TIMEZONE` | no | `Asia/Makassar` | Owner timezone |
| `CHART_TIME_OFFSET_HOURS` | no | `3` | Chart offset from UTC |
| `OHLC_PROVIDER` | no | `finnhub` | OHLC provider |
| `FINNHUB_API_KEY` | yes, Phase 2+ | - | Finnhub API key |
| `MIN_RADAR_MINUTES` | no | `5` | Minimum radar duration |
| `MIN_STRONG_MINUTES` | no | `14` | Strong pressure duration |
| `MAX_EVENT_GAP_SECONDS` | no | `300` | Max gap inside block |
| `SOFT_FINALIZE_SECONDS` | no | `90` | Soft finalizer delay |
| `HARD_FINALIZE_SECONDS` | no | `300` | Hard finalizer delay |
| `WEBHOOK_SECRET` | yes, Phase 3+ | - | Webhook auth secret |
| `DASHBOARD_BASIC_AUTH_USER` | recommended | - | Dashboard auth user |
| `DASHBOARD_BASIC_AUTH_PASSWORD` | recommended | - | Dashboard auth password |

---

## API Endpoints

### Health

```http
GET /health
```

Response:

```json
{
  "status": "ok",
  "service": "wolf15-signalthrottle-service"
}
```

### Replay logs

```http
POST /replay/logs
```

Quick live smoke test against Railway:

```bash
python scripts/replay_logs.py tests/fixtures/usdjpy_bplus_replay.log --url https://your-service.up.railway.app
```

This runs the recommended Phase 2 sequence:

```text
GET /health
GET /market/snapshot/USDJPY
POST /replay/logs
GET /signals/latest
```

Replay-only example:

```bash
python scripts/replay_logs.py tests/fixtures/usdjpy_bplus_replay.log --url https://your-service.up.railway.app --skip-health --skip-market
```

Payload:

```json
{
  "logs": "2026-04-24T02:30:34Z [SignalThrottle] USDJPY THROTTLED — 3 signals in last 300s (max 3)"
}
```

### Webhook log

```http
POST /webhook/log
```

Headers:

```text
X-Wolf15-Secret: your-secret
```

Payload:

```json
{
  "event": "signal_throttle",
  "symbol": "USDJPY",
  "timestamp_utc": "2026-04-24T02:45:03.883952Z",
  "message": "[SignalThrottle] USDJPY THROTTLED — 3 signals in last 300s (max 3)",
  "count": 3,
  "window_seconds": 300,
  "max_signals": 3,
  "source_service": "wolf15-engine",
  "pipeline_version": "v8.0"
}
```

### Latest signals

```http
GET /signals/latest
```

### Active blocks

```http
GET /blocks/active
```

### Signal detail

```http
GET /signals/{id}
```

---

## Dashboard

Dashboard minimal terdiri dari:

```text
1. Active Pressure
2. Priority A/A+ Signals
3. Latest Trade Plans
4. Signal Detail JSON
5. Outcome Tracking
```

Main cards:

```text
Active blocks
Priority signals
Avg density
Last update
```

Tables:

```text
Active pressure blocks
Latest finalized trade plans
Outcome by phase/grade
```

Signal detail page:

```text
metrics
time mapping
OHLC snapshot
chart phase
trade plan JSON
MFE/MAE result
```

---

## Signal Rules

### Block formation

```text
Block dimulai saat symbol muncul.
Block lanjut jika symbol sama dan gap <= 300 detik.
Block putus jika pair lain muncul.
Block putus jika gap > 300 detik.
```

### Pressure grading

```text
A+:
duration >= 20m
event_count >= 150
density >= 7/m
max_gap <= 60s

A:
duration >= 14m
event_count >= 100
density >= 7/m
max_gap <= 60s

A-:
duration >= 10m
density >= 7/m
max_gap <= 60s

B+:
duration >= 5m
density >= 5/m
max_gap <= 90s

C:
valid but weak density or large max gap
```

### Block relation

```text
0–10m    = CHAINED_CONTINUATION
10–30m   = SAME_PRESSURE_SEQUENCE
30–90m   = SAME_SESSION_RECHECK
>90m     = NEW_SESSION_SIGNAL
```

### Finalizer

```text
30s no new event     = COOLING
60–90s no new event  = SOFT_FINALIZED
300s no new event    = HARD_FINALIZED
pair replacement     = finalize previous block immediately
```

---

## Market Context

Timeframe roles:

```text
D1  = macro regime
H4  = master structure
H1  = entry location
M15 = timing / trigger
```

Supported phase labels:

```text
PIVOT_RECLAIM_CONTINUATION
HIGH_BASE_COMPRESSION
PULLBACK_TO_SUPPORT
BEARISH_PULLBACK_CONTINUATION
UPPER_RANGE_EXHAUSTION_RISK
SUPPORT_DECISION_ZONE
BREAKOUT_RETEST
BREAKDOWN_RETEST
RANGE_MID_NO_EDGE
UNCLASSIFIED
```

Action mapping:

```text
PIVOT_RECLAIM_CONTINUATION
→ BUY_ON_RETEST_OR_RECLAIM_HOLD

UPPER_RANGE_EXHAUSTION_RISK
→ PROTECT_LONG_OR_SELL_REJECTION

BEARISH_PULLBACK_CONTINUATION
→ SELL_ON_RALLY_OR_CONTINUATION

SUPPORT_DECISION_ZONE
→ WAIT_BREAKDOWN_OR_RECLAIM
```

---

## Outcome Tracking

Outcome tracker checks price after:

```text
15 minutes
30 minutes
60 minutes
```

Metrics:

```text
MFE_15m / MAE_15m
MFE_30m / MAE_30m
MFE_60m / MAE_60m
```

Result labels:

```text
FOLLOW_THROUGH_STRONG
FOLLOW_THROUGH_WEAK
NO_FOLLOW_THROUGH
REVERSAL_AGAINST_SIGNAL
CHOPPY_NO_EDGE
```

Performance aggregation:

```text
by symbol
by pressure_grade
by execution_grade
by chart_phase
by block_relation
```

---

## Engine Integration

MVP does not need live engine integration.

Recommended order:

```text
1. Manual replay logs
2. Test /webhook/log by curl
3. Enable webhook in engine with disabled flag
4. Deploy engine publisher
5. Enable publisher in Railway env
6. Monitor dashboard and engine logs
```

Engine environment:

```env
SIGNALTHROTTLE_WEBHOOK_ENABLED=1
SIGNALTHROTTLE_WEBHOOK_URL=https://wolf15-signalthrottle-service.up.railway.app/webhook/log
SIGNALTHROTTLE_WEBHOOK_SECRET=your-secret
```

Publisher requirements:

```text
timeout short
non-blocking
failure safe
no impact to Layer-12
no impact to order execution
```

---

## Security Notes

- Never commit `.env`.
- Never commit `FINNHUB_API_KEY`.
- Protect `/webhook/log` with `X-Wolf15-Secret`.
- Protect dashboard with Basic Auth or private Railway access.
- Use short timeout for engine publisher.
- Dashboard service failure must never block `wolf15-engine`.
- Keep trading output as advisory decision support, not automated execution.

---

## Testing

Run tests:

```bash
pytest -q
```

Suggested test coverage:

```text
parser extracts symbol/count/window
block detector splits by gap/pair
density and max_gap are correct
pressure grade rules are correct
timezone mapping is correct
phase classifier maps chart context correctly
trade_plan JSON has stable schema
duplicate webhook event is ignored
```

Replay fixture:

```bash
python scripts/replay_logs.py tests/fixtures/usdjpy_r7.log
```

---

## License & Disclaimer

This project follows the Wolf15/Tuyul Kartel educational and research-oriented trading tooling model.

Trading Forex/CFD involves risk of loss. Past performance does not guarantee future results. This dashboard is a decision-support and research tool, not financial advice and not an automated execution system.

See `LICENSE.txt` for the complete license and disclaimer.

---

## Status

Current target:

```text
Phase 1 — MVP Dashboard
```

Next target:

```text
Phase 2 — Market Context
```

---

## Maintainer

KELANA TJX / Wolf15 System
