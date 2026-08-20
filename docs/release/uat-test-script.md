# AI Marketing Factory - UAT Test Script

## Scope
This script validates end-to-end behavior for:
- Campaign creation and run
- Orchestrator queue processing
- Worker execution flow
- Validation/bundle outputs
- System operations and audit traceability

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

## Final UAT Sign-off
- Functional pass rate: ________%
- Blocking issues count: ________
- Go-live recommendation: Approve / Hold

Signatures:
- QA:
- Product:
- Ops:
