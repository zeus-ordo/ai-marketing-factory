# Task 3 Report

## Status

Deployed the independent context viewer to GCP VM `ai-marketing-factory` in project `market-factory`, zone `asia-east1-a`.

- Compose service: `context-viewer`
- Binding: `3010:3000`
- Database and viewer credentials: VM-local `/opt/ai-marketing-factory/.env.context-viewer`, mode `600`
- PostgreSQL: no published Compose port
- Deployed revision: `9d9147d`

## Verification

- `npm test -- test/query.test.ts`: 7 passing
- `npm run build` in `context-viewer`: passing locally
- Remote Docker build: passing
- Remote Compose status: `context-viewer` and all existing services `Up`
- Live viewer root: HTTP `200`
- Unauthenticated `/api/campaigns`: HTTP `401`
- Login: HTTP `200`; cookie flags include `HttpOnly` and `SameSite=Strict`
- Authenticated viewer root: HTTP `200`
- Existing frontend: HTTP `307` redirect, responding normally
- Filtered detail lookup: skipped because no captured context row was available on the deployed database

## Commits

- `2deb3cf` Deploy independent LLM context viewer
- `9d9147d` Fix context viewer Docker build context

## Concerns

- Historical rows created before capture deployment may lack exact prompts or persisted worker payloads.
- No captured context was available for live prompt/detail verification.
- The local Next build emits the known non-failing multiple-lockfile workspace-root warning.
- Remote `npm install` reports dependency advisories from the existing lockfile; the image build still succeeds.

## Review Fix Verification

Audit checks were run against project `market-factory`, VM `ai-marketing-factory`, zone `asia-east1-a`.

- Remote audit UTC timestamp: `2026-09-12T11:58:53Z`
- Public root audit UTC timestamp: `2026-09-12T11:58:57Z`
- Firewall rule: `allow-ai-marketing-context-viewer-3010`
- Firewall description: `Public direct access for authenticated context viewer on TCP 3010; viewer login is mandatory`
- Firewall scope: ingress `tcp:3010`, source `0.0.0.0/0`, target tag `ai-marketing-factory`, disabled `false`
- PostgreSQL: no published Compose port

### Compose PS

At the remote audit timestamp, all services were `Up`:

```text
caddy Up
campaign-service Up
context-viewer Up 0.0.0.0:3010->3000/tcp
decision-service Up
frontend Up
membership-service Up
orchestrator Up
worker-ads Up
worker-copy Up
worker-image Up
worker-video Up
```

### HTTP Checks

- Localhost viewer root: `200`
- Public viewer root `http://35.221.249.149:3010/`: `200`
- Unauthenticated localhost `/api/campaigns`: `401`
- Login: `200`
- Login cookie flags: `HttpOnly`, `SameSite=Strict`
- Existing frontend: `307`

Credentials and cookie values were not printed.
