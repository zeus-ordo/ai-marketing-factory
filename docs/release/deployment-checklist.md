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
2. [ ] Restore previous known-good image tags
3. [ ] Re-attach previous env secrets/config
4. [ ] Validate `/health` and core APIs
5. [ ] Announce rollback completion

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

---

## 6) Sign-off
- QA sign-off: 
- Product sign-off:
- Ops sign-off:
- Final go-live decision:
