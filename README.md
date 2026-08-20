This is a [Next.js](https://nextjs.org) project bootstrapped with [`create-next-app`](https://nextjs.org/docs/app/api-reference/cli/create-next-app).

## Getting Started

First, run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

## Milestone 1 Developer Workflow

This repository now includes startup and diagnostics scripts for stable local development.

### Windows 一鍵啟動（新電腦建議）

```powershell
npm run dev:bootstrap:win
```

或直接在檔案總管雙擊：

```text
一鍵啟動.bat
```

這會自動執行：
- `npm install`
- `python -m pip install -r services/campaign_service/requirements.txt`
- 若 `.env.local` 不存在，從 `.env.example` 建立
- `npm run dev:doctor`
- `npm run dev:up`

### 1) Verify environment before startup

```bash
npm run dev:doctor
```

Checks:
- required env vars (`CHATBOT_INTERNAL_API_KEY`, and `POSTGRES_DSN` when `CAMPAIGN_REQUIRE_POSTGRES=true`)
- `.env.local` existence
- Python dependencies (`psycopg`, `uvicorn`, `fastapi`, `pydantic`, `python-multipart`)
- npm availability
- `CAMPAIGN_REQUIRE_POSTGRES` effective mode (`true`/`false`)
- local ports (`DEV_FRONTEND_PORT`, `DEV_BACKEND_PORT`; default `3000`, `8080`)

### 2) Start frontend + campaign service together

```bash
npm run dev:up
```

This starts:
- Next.js frontend (`:DEV_FRONTEND_PORT`, default `:3000`)
- campaign service (`:DEV_BACKEND_PORT`, default `:8080`)

You can override both ports in `.env.local`:

```text
DEV_FRONTEND_PORT=3000
DEV_BACKEND_PORT=18080
NEXT_PUBLIC_CAMPAIGN_API_BASE=http://localhost:18080
```

Logs are written to:

```text
.sisyphus/runtime-logs/frontend.*.log
.sisyphus/runtime-logs/campaign-api.*.log
```

### 3) Backend preflight fail-fast

Campaign service will fail startup if:
- `CHATBOT_INTERNAL_API_KEY` is missing
- `CAMPAIGN_REQUIRE_POSTGRES=true` and `POSTGRES_DSN` is missing/unreachable

Set in env:

```text
CAMPAIGN_REQUIRE_POSTGRES=true
POSTGRES_DSN=postgresql://...
```

You can start editing the page by modifying `app/page.tsx`. The page auto-updates as you edit the file.

This project uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to automatically optimize and load [Geist](https://vercel.com/font), a new font family for Vercel.

## Learn More

To learn more about Next.js, take a look at the following resources:

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API.
- [Learn Next.js](https://nextjs.org/learn) - an interactive Next.js tutorial.

You can check out [the Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!

## Deploy on Vercel

The easiest way to deploy your Next.js app is to use the [Vercel Platform](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=create-next-app&utm_campaign=create-next-app-readme) from the creators of Next.js.

Check out our [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.

## System Ops Checklist (P0-P2)

### P0: Secrets and authenticated checks

1. Copy `.env.test.local.example` to `.env.test.local` and fill real credentials.
2. Ensure `.env.local` secrets are non-default.

```bash
npm run check:secrets
npm run check:api:regression
npm run smoke:e2e:oneclick
```

### P1: Stable compose routing

- `deploy/Caddyfile` now routes by compose service names (`campaign-service`, `membership-service`) instead of `host.docker.internal`.
- Frontend runs as immutable production image via `deploy/Dockerfile.frontend`.

### P2: Queue maintenance

Trim stream history while preserving recent records:

```bash
npm run ops:trim-queues
```

Optional envs:

```text
OPS_BASE_URL=http://localhost:8080
OPS_QUEUE_TRIM_MAXLEN=200
OPS_OPERATOR=maintenance
```
