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

---

## 4) SLO/SLA Watch Window (First 2 hours)
- [ ] No stuck tasks > 10 minutes
- [ ] Retry rate within expected threshold
- [ ] DLQ growth rate acceptable
- [ ] API error rate within baseline
- [ ] No critical security/auth errors

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

---

## 6) Sign-off
- QA sign-off: 
- Product sign-off:
- Ops sign-off:
- Final go-live decision:
