# AI Marketing Factory - UAT Test Script

## Scope
This script validates end-to-end behavior for:
- Campaign creation and run
- Orchestrator queue processing
- Worker execution flow
- Validation/bundle outputs
- System operations and audit traceability

## Automated Acceptance Gate
Run the deterministic acceptance suite before the live-service UAT. It uses
in-process fixtures and never calls Google, Gemini, PostgreSQL, Redis, or a
worker provider:

```bash
python -m pytest tests_e2e/test_complete_campaign_flow.py -q
```

The suite covers required and conditional validation, reference priority and
75:25 context accounting, disabled/failed/redacted search, context restart
hydration, isolated worker failures, bounded and single-task retry, review
diagnostics/run filtering, empty-result rejection, provider/model metadata,
and UI/OpenAPI contracts. The live company-isolation checks remain marked
`e2e`, are skipped unless `RUN_LIVE_E2E=1`, and require the services described
in `tests_e2e/conftest.py`.

## Test Environment
- Base URL: ____________________
- Tester: ____________________
- Date: ____________________

---

## UAT-01: Create Campaign
**Steps**
1. Open `/campaigns`
2. Click **Create Sample Campaign** (or submit custom brief)

**Expected**
- Campaign row appears in table
- Status is `draft` (or initial expected state)

Result: Pass / Fail  
Notes:

---

## UAT-02: Run Workflow
**Steps**
1. On `/campaigns`, click **Run** for a campaign
2. Open `/workflow`

**Expected**
- Task states progress via orchestrator (planned/running/passed...)
- No permanent stuck state without DLQ/audit evidence

Result: Pass / Fail  
Notes:

---

## UAT-03: Content Validation Output
**Steps**
1. Open `/content-studio`
2. Observe generated assets and confidence/pass-fail

**Expected**
- Validation data displayed for selected campaign
- Pass/Fail badges and confidence values rendered

Result: Pass / Fail  
Notes:

---

## UAT-04: Bundle Retrieval
**Steps**
1. Call `GET /api/v1/campaigns/{campaign_id}/bundle`

**Expected**
- Response includes `copy_assets`, `image_assets`, `video_assets`, `ads_strategy`
- Structure matches API contract

Result: Pass / Fail  
Notes:

---

## UAT-05: Queue Health Dashboard
**Steps**
1. Open `/system`
2. Verify queue topic metrics and DLQ section

**Expected**
- Topic length/pending/lag visible
- DLQ list visible (or "No DLQ events")

Result: Pass / Fail  
Notes:

---

## UAT-06: System Ops - Health Check
**Steps**
1. Enter operator name
2. Click **Run Health Check**

**Expected**
- Redis/worker status returned
- Operation log entry created with operator + result

Result: Pass / Fail  
Notes:

---

## UAT-07: System Ops - Retry DLQ
**Precondition**
- At least one DLQ item exists

**Steps**
1. In DLQ panel, click **Retry** on one item

**Expected**
- Item removed from DLQ list (or status updated)
- Audit log entry created

Result: Pass / Fail  
Notes:

---

## UAT-08: Audit Query Filters
**Steps**
1. In `/system`, set operator/operation/result filters
2. Add `From (ISO)` and `To (ISO)`
3. Click **Apply**

**Expected**
- Audit table shows filtered entries
- Pagination works (Prev/Next)

Result: Pass / Fail  
Notes:

---

## UAT-09: Audit CSV Export
**Steps**
1. Apply filters in `/system`
2. Click **Export CSV**

**Expected**
- CSV downloads successfully
- CSV rows reflect active filters

Result: Pass / Fail  
Notes:

---

## UAT-10: Safety Controls
**Steps**
1. Attempt high-frequency operations rapidly
2. Observe system response

**Expected**
- Rate limiting protects endpoints (429 where expected)
- UI shows clear feedback

Result: Pass / Fail  
Notes:

---

## UAT-11: Generation Context and Failure Recovery
**Steps**
1. Create a temporary campaign with an immediate upload and an industry match.
2. Run it with `EXTERNAL_SEARCH_PROVIDER=disabled` in environments without a
   configured search secret.
3. Verify the campaign diagnostics show source provenance, token counts, and
   internal/external ratios without source content or secrets.
4. Simulate a worker quota failure, then retry only the failed task.

**Expected**
- The failed task is terminal and retryable; descendants are `blocked` while
  unrelated tasks continue.
- Retry resets only the failed branch and preserves the same run context.
- Repeated automatic failures stop at `WORKER_RETRY_MAX_ATTEMPTS`; no task
  remains indefinitely pending.
- Review diagnostics can be filtered by `run_id` and never mix runs.

Result: Pass / Fail
Notes:

---

## UAT-12: Restart and Reconciliation
**Steps**
1. Stop/restart campaign-service after a run snapshot has been persisted.
2. Reload the campaign and review pages.
3. If a manual retry dispatch fails, inspect task state and retry/reconciliation
   logs before attempting another retry.

**Expected**
- The immutable generation context and its provenance are hydrated from storage
  after a cold cache.
- A failed manual retry is reconciled to a terminal, retryable state; if the
  database reports zero affected rows, operations receives a recovery-pending
  alert rather than a false success.
- Previous task attempts remain available for audit.

Result: Pass / Fail
Notes:

---

## Final UAT Sign-off
- Functional pass rate: ________%
- Blocking issues count: ________
- Go-live recommendation: Approve / Hold

Signatures:
- QA:
- Product:
- Ops:
