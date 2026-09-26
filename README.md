# FF Gateway — Free Fire Player Info Gateway

Production-ready Python microservice that fetches live Free Fire player data
from Garena's internal Protobuf API and exposes a clean REST API for the
Esporizon backend.

---

## Architecture

```
┌─────────────────────────┐
│  React Frontend (Vercel)│  ← Layer 1 (existing)
└────────────┬────────────┘
             │ HTTPS
┌────────────▼────────────┐
│ Node.js Backend (Azure) │  ← Layer 2 (existing, add FREEFIRE_API_URL)
└────────────┬────────────┘
             │ HTTPS GET /player/{uid}?region=IND
┌────────────▼────────────────────────────────────────────────┐
│                  FF Gateway (THIS SERVICE)                   │
│                                                              │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────────┐  │
│  │ Token Mgr   │  │ Cache Layer  │  │ Circuit Breaker   │  │
│  │ (auto JWT)  │  │ LRU + Redis  │  │ (per region)      │  │
│  └──────┬──────┘  └──────┬───────┘  └─────────┬─────────┘  │
│         │                │                     │             │
│  ┌──────▼────────────────▼─────────────────────▼──────────┐ │
│  │              Garena API Client                          │ │
│  │   Protobuf Serialize → AES-128-CBC Encrypt → HTTPS POST│ │
│  └──────────────────────────────────────────────────────-─┘ │
└────────────────────────────┬────────────────────────────────┘
                             │ AES-encrypted Protobuf
              ┌──────────────▼───────────────────┐
              │   Garena Regional Cluster         │
              │ client.ind.freefiremobile.com     │
              │ client.us.freefiremobile.com  etc │
              └──────────────────────────────────┘
```

---

## API Endpoints

### `GET /health`
```json
{
  "status": "healthy",
  "uptime_seconds": 3600,
  "token_age_seconds": 120,
  "token_expires_in_seconds": 15638200,
  "last_refresh": "2026-09-26T10:00:00+00:00",
  "region_support": ["BD", "BR", "EG", "ID", "IND", "ME", "PK", "SAC", "SG", "TH", "VN"],
  "circuit_breakers": { "garena:IND": "CLOSED" }
}
```

### `GET /player/{uid}?region=IND`
```bash
curl "https://your-gateway.azurewebsites.net/player/1036762440?region=IND"
```
```json
{
  "success": true,
  "cached": false,
  "fetched_at": "2026-09-26T10:00:00+00:00",
  "uid": "1036762440",
  "region": "IND",
  "basic_info": {
    "nickname": "PlayerName",
    "level": 45,
    "exp": 123456,
    "likes": 1000,
    "avatar_url": "https://cdn.jsdelivr.net/gh/ShahGCreator/icon@main/PNG/902000270.png"
  },
  "rank_info": { "br_rank": 300, "br_ranking_points": 4200 },
  "clan_info": { "clan_name": "EliteSquad", "clan_level": 5 },
  "credit_score_info": { "score": 100, "status": "PERFECT", "is_tournament_eligible": true }
}
```

### `GET /version`
```json
{
  "service": "ff-gateway",
  "version": "1.0.0",
  "ob_version": "OB55",
  "build_date": "2026-09-26",
  "git_commit": "abc1234"
}
```

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `FF_GUEST_UID` | ✅ | — | Garena guest account UID |
| `FF_GUEST_PASSWORD` | ✅ | — | Garena guest account password |
| `FF_GUEST_TOKEN` | ❌ | — | Static JWT override (skips login) |
| `FF_OB_VERSION` | ❌ | `OB55` | Garena release version header |
| `AES_KEY` | ❌ | `Yg&tc%DEuh6%Zc^8` | AES-128-CBC key (16 bytes) |
| `AES_IV` | ❌ | `6oyZDr22E3ychjM%` | AES-128-CBC IV (16 bytes) |
| `PORT` | ❌ | `8000` | Server port |
| `LOG_LEVEL` | ❌ | `INFO` | Logging level |
| `REDIS_URL` | ❌ | — | Redis connection URL |
| `ENABLE_CACHE` | ❌ | `true` | Enable player data cache |
| `CACHE_TTL_SECONDS` | ❌ | `300` | Cache TTL (5 minutes) |
| `ENABLE_RATE_LIMIT` | ❌ | `true` | Enable per-UID rate limiting |
| `RATE_LIMIT_PER_UID` | ❌ | `10` | Max requests/minute per UID |
| `CIRCUIT_BREAKER_THRESHOLD` | ❌ | `5` | Failures before circuit opens |
| `CIRCUIT_BREAKER_RESET_SECONDS` | ❌ | `60` | Seconds before circuit half-opens |
| `CORS_ORIGINS` | ❌ | `*` | Allowed CORS origins |

---

## Local Setup

### Option A: Direct Python

```bash
cd ff-gateway
python -m venv .venv
source .venv/bin/activate         # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt

cp .env.example .env
# Edit .env with your FF_GUEST_UID and FF_GUEST_PASSWORD

python src/app.py
# OR via gunicorn:
# gunicorn --workers 2 --timeout 60 --bind 0.0.0.0:8000 src.app:app
```

### Option B: Docker

```bash
cd ff-gateway
cp .env.example .env
# Edit .env

docker compose up --build

# With Redis cache:
docker compose --profile redis up --build
```

---

## Running Tests

```bash
cd ff-gateway
pytest tests/ --cov=src --cov-report=term-missing -v
```

---

## Updating for a New OB Version (e.g., OB56)

1. Change `FF_OB_VERSION=OB56` in Azure Application Settings (or `.env`)
2. If Garena changed AES keys, update `AES_KEY` and `AES_IV` env vars
3. If Garena changed protobuf schemas, regenerate stubs:
   ```bash
   ./scripts/regen_protobuf.sh
   ```
4. If Garena changed regional hostnames, update `src/ff/regions.py`
5. Redeploy — push to `main` triggers CI/CD automatically

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---|---|---|
| `401 Unauthorized` from Garena | JWT expired | Check `/health` → `token_expires_in_seconds`. Gateway auto-refreshes. If `0`, check `FF_GUEST_UID`/`FF_GUEST_PASSWORD`. |
| `400 Bad Request` from Garena | Wrong OB version | Update `FF_OB_VERSION` env var |
| `503 Service Unavailable` | Circuit breaker open | Check `/health` → `circuit_breakers`. Wait 60s or restart. |
| `/health` shows `degraded` | Token refresh failed 3x | Check logs for auth errors. Verify guest credentials. |
| Player data is stale | Cache hit | Cache TTL is 5 min. Pass `?nocache=1` to bypass (not implemented — delete Redis key if needed) |
| Cold start delay | Azure App Service | Normal — first request after idle takes 5-15s. Use "Always On" in Azure. |
