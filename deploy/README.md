# Deploy Baseline (Sprint 1)

This folder provides the minimum deployment baseline for local development.

## Included services

- `campaign-service` (FastAPI)
- `decision-service` (Task plan generation)
- `orchestrator` (Task state machine)
- `worker-copy`
- `worker-image`
- `worker-video`
- `worker-ads`
- `postgres`
- `redis`

## Start

```bash
docker compose -f deploy/docker-compose.yml up --build
```

Campaign API will be available at `http://localhost:8080`.
