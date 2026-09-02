# SDD ledger — plan: docs/superpowers/plans/2026-09-01-complete-campaign-generation-flow.md

Baseline: d20eadd
Task 1: complete (commit 0168cd1, review clean; minor: no-side-effect test scope)
Task 2: complete (commits 6c28c5f..31fc9f5, review clean)
Task 3: complete (commits 6c86a57..f314a51, review clean)
Task 4: complete (commits 73e1c34..9a00166, review clean; minor: restart no-run fallback coverage)
Task 5: pending
Task 6: pending
Task 7: pending

## Task 7 Report

- Added deterministic `tests_e2e/test_complete_campaign_flow.py` coverage for
  validation, reference priority and 75:25 budgeting, search modes/failures,
  restart hydration, worker isolation, bounded/single-task retry, review run
  filtering, empty results, provider/model metadata, and UI/OpenAPI contracts.
- Restricted the existing live-service skip behavior to tests marked `e2e`, so
  offline acceptance tests always execute.
- Updated UAT and deployment checklists and added
  `docs/release/complete-campaign-flow-runbook.md` with configuration, secret,
  migration, alert, retry, reconciliation, restart, and verification guidance.

## Task 7 Review Follow-up Report

- Replaced source-only acceptance checks with ASGI TestClient coverage for
  campaign create/run, worker result ingest, review filtering, and single-task
  retry, using mocked search, worker, decision, orchestrator, and persistence
  boundaries.
- Removed collection-time localhost probes; live E2E is now explicitly opt-in
  with `RUN_LIVE_E2E=1`.
- Standardized the runtime, example, and GCP compose search default to
  `disabled`, and documented `not_configured`.
- Documented campaign-service `WORKER_RETRY_MAX_ATTEMPTS` separately from the
  orchestrator source-level `MAX_RETRY = 2` and manual retry limit.

## Task 7 Secret and Source-Check Follow-up Report

- Removed tracked local secret override files and replaced hardcoded compose
  credentials with runtime environment placeholders; added ignore rules for
  future local override/secret files.
- Expanded `scripts/check-secrets.mjs` to scan tracked dotenv/YAML/config files
  while reporting only file/key identifiers.
- Replaced page-source assertions with route-backed OpenAPI assertions; all
  deterministic flow checks use ASGI TestClient and offline fixtures.

## Task 7 Repository Secret Hygiene Report

- Removed hardcoded database and weak API-key defaults from tracked deployment
  and startup files; required runtime environment variables now fail clearly
  without printing values.
- Expanded the tracked-config scanner to cover dotenv, YAML/JSON, shell,
  PowerShell, batch, TypeScript, and Python files, including interpolation
  fallbacks, DSN credentials, and literal key assignments.
- Added scanner regression coverage for DSNs, batch assignments, and safe/unsafe
  interpolation; no credential values are included in scanner output.
