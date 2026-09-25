# AI Marketing Factory - Deployment Checklist (Release Gate)

## 0) Release Metadata
- Release version:
- Release date/time (Asia/Taipei):
- Release owner:
- Approver:

---

## 1) Pre-Deployment Checks
- [ ] `npm run lint` passes
- [ ] `npm run build` passes
- [ ] Python compile passes for all services
- [ ] No unresolved P0/P1 defects
- [ ] `.env` values set for target environment
- [ ] DB backup snapshot completed
- [ ] Redis persistence/backup policy confirmed
- [ ] Run deterministic acceptance coverage: `python -m pytest tests_e2e/test_complete_campaign_flow.py -q`
- [ ] Run deterministic permissions/folder coverage: `python -m pytest tests_e2e/test_permissions_and_folder_scope.py -q`
- [ ] Run service regression coverage: `pytest services/campaign_service -q` and `pytest services/orchestrator -q`

### Required environment keys
- [ ] `POSTGRES_DSN`
- [ ] `REDIS_URL`
- [ ] `OPENCLAW_CONTROLLER_URL`
- [ ] `DECISION_SERVICE_URL`
- [ ] `WORKER_COPY_URL`
- [ ] `WORKER_IMAGE_URL`
- [ ] `WORKER_VIDEO_URL`
- [ ] `WORKER_ADS_URL`
- [ ] `JWT_SECRET`
- [ ] `EXTERNAL_SEARCH_PROVIDER` (`disabled` is the safe default)
- [ ] `EXTERNAL_SEARCH_API_KEY` (Secret Manager/VM secret file only when Google search is enabled)
- [ ] `EXTERNAL_SEARCH_ENGINE_ID` (configuration value; do not put the API key in Git)
- [ ] Campaign-service `WORKER_RETRY_MAX_ATTEMPTS` and `WORKER_RETRY_BACKOFF_SECONDS`
- [ ] `MANUAL_RETRY_MAX_ATTEMPTS`
- [ ] Orchestrator automatic retry is verified against hardcoded `MAX_RETRY = 2` and 300-second cap in `services/orchestrator/app/main.py`

---

## 2) Deployment Steps (Staging -> Production)

### Staging smoke
- [ ] `docker compose -f deploy/docker-compose.yml up --build -d`
- [ ] Health endpoints all return 200:
  - [ ] campaign-service `/health`
  - [ ] decision-service `/health`
  - [ ] orchestrator `/health`
  - [ ] worker-copy `/health`
  - [ ] worker-image `/health`
  - [ ] worker-video `/health`
  - [ ] worker-ads `/health`
- [ ] Run one full campaign flow and confirm `/workflow`, `/content-studio`, `/system`

### Production rollout
- [ ] Deploy image set (immutable tags)
- [ ] Check out the approved commit on `ai-marketing-factory` before deploying the independent context viewer.
- [ ] Create `/opt/ai-marketing-factory/.env.context-viewer` from `deploy/context-viewer.env.example`, set `DATABASE_URL`, `VIEWER_USERNAME`, `VIEWER_PASSWORD`, and `SESSION_SECRET`, and restrict it to mode `600`; never print its values.
- [ ] Deploy the viewer only through `docker compose -f deploy/docker-compose.gcp.yml up -d --build context-viewer`.
- [ ] Ensure firewall rule `allow-ai-marketing-context-viewer-3010` allows `tcp:3010` from `0.0.0.0/0` to target tag `ai-marketing-factory`; this direct public-IP design requires viewer login authentication for every user.
- [ ] Confirm the viewer is available at `http://35.221.249.149:3010`; PostgreSQL must not have a published port.
- [ ] Run DB migration/init (if applicable)
- [ ] Apply additive campaign-service migrations before traffic. Never drop or rewrite existing campaign/reference tables.
- [ ] Confirm `generation_contexts`, `generation_context_items`, and task-attempt columns exist; snapshots are immutable and keyed by campaign run.
- [ ] Confirm additive `folders.folder_id`/scope schema and `folder_id` associations exist without dropping legacy data.
- [ ] Verify existing folder/reference counts and association integrity before accepting traffic.
- [ ] Verify orchestrator consumer loop active
- [ ] Verify Redis stream group exists for:
  - [ ] `task.copy`
  - [ ] `task.image`
  - [ ] `task.video`
  - [ ] `task.ads`
  - [ ] `task.dlq`

---

## 3) Post-Deployment Validation
- [ ] Create campaign from `/campaigns`
- [ ] Start run and verify status progression in `/workflow`
- [ ] Verify validation results in `/content-studio`
- [ ] Verify queue health panel in `/system`
- [ ] Verify operations:
  - [ ] health check
  - [ ] purge topic (non-prod only or controlled)
  - [ ] retry DLQ
- [ ] Verify audit logs record operator/action/result
- [ ] Verify audit CSV export works with filters
- [ ] Verify diagnostics are scoped to the selected `run_id` and show provider/model names only
- [ ] Verify Manager review access and platform-folder read/use-only behavior.
- [ ] Verify company-admin same-company role assignment rejects platform and cross-company roles.
- [ ] Verify platform-admin folder mutation and company folder isolation.
- [ ] Restart the service and verify knowledge/reference `folder_id` associations remain readable.
- [ ] Preserve local folder store until backend persistence/read verification is complete.

### Independent LLM context viewer validation
- [ ] Public URL: `http://35.221.249.149:3010`; authentication is mandatory even though the listener is publicly reachable.
- [ ] `GET http://localhost:3010/api/campaigns` without the session cookie returns `401`.
- [ ] `GET http://35.221.249.149:3010/` returns `200`.
- [ ] Login with the configured viewer credentials succeeds and sets an HttpOnly, SameSite cookie.
- [ ] Authenticated `GET http://localhost:3010/` returns `200`.
- [ ] Authenticated filtered detail lookup returns the captured prompt for a known `generation_context_id` when one is available.
- [ ] Existing Compose services remain `Up` and the original frontend still responds normally.
- [ ] Do not treat pre-capture rows as evidence of an exact prompt; historical rows may lack captured worker prompts and payloads.

---

## 4) SLO/SLA Watch Window (First 2 hours)
- [ ] No stuck tasks > 10 minutes
- [ ] Retry rate within expected threshold
- [ ] DLQ growth rate acceptable
- [ ] API error rate within baseline
- [ ] No critical security/auth errors
- [ ] No `worker_dispatch_failed`, `persistence_error`, `recovery_pending`, or external-search error spike beyond the agreed baseline
- [ ] Alert on growing blocked-task count, DLQ growth, retry exhaustion, or missing context hydration

---

## 5) Rollback Plan
Trigger rollback if any of:
- P0 outage > 10 min
- Data corruption risk
- Queue processing halted and unrecoverable quickly

Rollback actions:
1. [ ] Scale down/stop new release services
2. [ ] If the viewer is the only failing component, run `docker compose -f deploy/docker-compose.gcp.yml stop context-viewer` and leave the original services running
3. [ ] Restore previous known-good image tags
4. [ ] Re-attach previous env secrets/config
5. [ ] Validate `/health` and core APIs
6. [ ] Announce rollback completion

Data actions:
- [ ] If schema changed, follow backward migration/restore snapshot playbook
- [ ] Preserve failed release logs for incident review

### Retry and reconciliation operations
- Automatic worker retries are finite and exponentially delayed; the delay is
  capped by the orchestrator and terminal failures are recorded before
  descendants are blocked.
- Use the single-task retry action for a failed task. Do not manually replay a
  whole run unless the run itself is being regenerated.
- If persistence fails after dispatch, leave the message pending for recovery;
  do not acknowledge it manually. Check the reconciler and audit log before a
  second action.
- After restart, confirm consumer groups, pending-message reclamation, and
  generation-context hydration before accepting new runs.

## 5.1) Image Generation and Batch Upload Hardening
- [ ] Run `python -m pytest tests_e2e/test_image_generation_and_batch_upload.py -q`
- [ ] Confirm empty real image responses fail and valid image responses persist an asset.
- [ ] Confirm 1-, 2-, and 10-file batches, including an intentional failure, keep campaign start blocked until retry succeeds.
- [ ] Confirm a persistence/service restart preserves uploaded metadata and file bytes.
- [ ] Create and verify a Cloud SQL backup before any production persistence/schema change:
  `gcloud sql backups create --project=market-factory --instance=ai-marketing-postgres --description="image-batch-pre-deploy-${COMMIT}"`
- [ ] Deploy the approved commit only through `deploy/docker-compose.gcp.yml`; do not print environment values.
- [ ] Record Compose service status, public route health, neutral image smoke provider/status/attempts/asset count, and upload batch results in `task-5-report.md`.
- [ ] Keep local reference/generated stores until backend persistence and restart readability are verified.

---

## 6) Sign-off
- QA sign-off: 
- Product sign-off:
- Ops sign-off:
- Final go-live decision:
