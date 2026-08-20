# Campaign Service (MVP)

Minimal FastAPI service for Sprint 1 baseline.

## Endpoints

- `POST /api/v1/campaigns`
- `GET /api/v1/campaigns/{campaign_id}`
- `GET /api/v1/campaigns`
- `POST /api/v1/campaigns/{campaign_id}/run`
- `GET /api/v1/campaigns/{campaign_id}/tasks`

## Run locally

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```
