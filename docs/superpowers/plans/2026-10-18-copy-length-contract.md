# Copy Length Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make initial and regenerated copy obey the requested format length, including 300–500 characters for public-relations copy.

**Architecture:** campaign-service derives a structured body-length contract from the campaign brief and sends it on every copy worker request. worker_copy uses that contract in both normal and regeneration prompts, validates model output by Unicode character count, and makes one bounded repair request before returning an error for an invalid result.

**Tech Stack:** FastAPI/Pydantic, Python, httpx, pytest, Docker Compose/GCP.

## Global Constraints

- 宣傳文宣: maximum 100 characters.
- 社群文章: 100–200 characters.
- 公關稿: 300–500 characters.
- The fixed `body 80-200 chars` rule must not remain in normal or regeneration prompt construction.
- Existing JSON response keys remain exactly `title`, `body`, and `cta`.
- Existing title max 30 and CTA max 15 constraints remain unchanged.
- Older worker callers without a length contract retain a default 80–200 range.
- Initial generation and regeneration use the same length validation and repair path.

---

### Task 1: Add a structured copy-length contract to campaign-service

**Files:**
- Modify: `services/campaign_service/app/main.py` near prompt/payload helpers around `build_copy_generation_prompt`, `build_campaign_brand_context`, and copy worker payload construction around lines 3350–3410, 3525–3560, and 6060–6090.
- Test: `services/campaign_service/test_copy_length_contract.py` (create).

**Interfaces:**
- Produces `body_min_length: int` and `body_max_length: int` in normal copy worker payloads and copy regeneration payloads.
- Adds a deterministic helper with a stable signature such as `get_copy_body_length_contract(campaign: CampaignRecord) -> dict[str, int]`.

- [ ] **Step 1: Write failing contract tests.**

Create campaign fixtures whose `project_description` contains `公關稿`, `社群文章`, and `宣傳文宣`. Assert each maps to the intended min/max values, and assert the payload sent to the copy worker contains those exact fields for both initial generation and regeneration.

```python
assert get_copy_body_length_contract(public_relations_campaign) == {
    "body_min_length": 300,
    "body_max_length": 500,
}
```

- [ ] **Step 2: Run the focused tests and confirm they fail.**

Run: `python -m pytest -q services/campaign_service/test_copy_length_contract.py`

Expected: FAIL because no structured length helper/worker payload fields exist.

- [ ] **Step 3: Implement deterministic contract selection.**

Normalize the campaign project description and match explicit public-relations terms (`公關稿`, `新聞稿`, `press release`, `public relations`) before social terms and promotional terms. Use the backward-compatible 80–200 range when no explicit format is present. Add the returned fields to every initial and regeneration copy worker request without removing the natural-language Copy type policy.

- [ ] **Step 4: Run campaign-service contract tests and existing copy-related tests.**

Run: `python -m pytest -q services/campaign_service/test_copy_length_contract.py services/campaign_service/test_task6_routes.py`

Expected: all tests pass.

- [ ] **Step 5: Commit the campaign-service contract.**

```bash
git add services/campaign_service/app/main.py services/campaign_service/test_copy_length_contract.py
git commit -m "feat: pass copy body length contract to worker"
```

### Task 2: Make worker_copy obey and validate the contract

**Files:**
- Modify: `services/worker_copy/app/schemas.py` — add optional `body_min_length` and `body_max_length` to `CopyRunRequest` and `RevisionRequest`, defaulting to 80 and 200, with validation that min is non-negative and max is at least min.
- Modify: `services/worker_copy/app/main.py` — centralize dynamic field rules, remove both hard-coded `body 80-200 chars` strings, validate parsed variants, and perform one repair request for invalid body lengths in both normal and regeneration flows.
- Test: `services/worker_copy/test_copy_length.py` (create).

**Interfaces:**
- Consumes `CopyRunRequest.body_min_length/body_max_length` and `RevisionRequest.body_min_length/body_max_length`.
- Produces the unchanged `CopyRunResponse` JSON shape or HTTP 502 with a clear invalid-length detail after repair failure.

- [ ] **Step 1: Write failing worker tests.**

Use mocked `httpx.Client` responses to cover: dynamic 300–500 prompt text with no fixed 80–200 rule; valid public-relations output; one repair for invalid output; 502 after invalid repair; regeneration using the same path; and default 80–200 for old callers.

- [ ] **Step 2: Run worker tests and confirm they fail.**

Run: `python -m pytest -q services/worker_copy/test_copy_length.py`

Expected: FAIL because the schemas lack fields, prompts contain the fixed range, and no validation/repair helper exists.

- [ ] **Step 3: Implement shared length helpers.**

Add helpers with explicit signatures:

```python
def body_length_is_valid(body: str, minimum: int, maximum: int) -> bool: ...
def copy_field_rules(minimum: int, maximum: int) -> str: ...
def repair_copy_variant(...): ...
```

Use `len(body)` for Unicode character count. Build the same JSON field rules for initial and regeneration requests. The repair prompt must include the exact range, the invalid body, and the existing `title/body/cta` JSON contract without exposing provider secrets.

- [ ] **Step 4: Replace both hard-coded prompt suffixes and validate every variant.**

Use the dynamic field-rule helper in the normal request around `main.py:167–171` and regeneration request around `main.py:280–284`. Parse JSON, validate title/CTA non-empty and body range, repair once when body length is invalid, then construct `CopyVariant`. Keep stub mode backward-compatible but generate a body within the requested range or explicitly reject stub mode when it cannot satisfy the contract.

- [ ] **Step 5: Run worker tests and full worker suite.**

Run: `python -m pytest -q services/worker_copy/test_copy_length.py` and `python -m pytest -q services/worker_copy`.

Expected: all tests pass.

- [ ] **Step 6: Commit worker changes.**

```bash
git add services/worker_copy/app/schemas.py services/worker_copy/app/main.py services/worker_copy/test_copy_length.py
git commit -m "feat: validate copy body length in worker"
```

### Task 3: Verify end-to-end contract and deploy

**Files:**
- Verify: `services/campaign_service`, `services/worker_copy`, deployment compose files.
- Modify only if a focused verification failure identifies a scoped contract issue.

- [ ] **Step 1: Run complete backend suites.**

Run from repository root:

```powershell
$env:PYTHONPATH = (Get-Location).Path
$env:CHATBOT_INTERNAL_API_KEY = "test-key"
python -m pytest -q services/campaign_service
python -m pytest -q services/worker_copy
```

Expected: zero failures; existing deprecation warnings may remain.

- [ ] **Step 2: Run static checks.**

Run: `git diff --check` and confirm no fixed `body 80-200 chars` string remains in `services/worker_copy/app`.

- [ ] **Step 3: Push and deploy affected services.**

Push the feature branch, update the GCP checkout, rebuild `campaign-service` and `worker-copy`, and recreate those services with `deploy/docker-compose.gcp.yml`.

- [ ] **Step 4: Run production smoke with a temporary copy request.**

Use an authenticated test request whose description explicitly says `公關稿` and whose deliverables request one copy variant. Verify the worker payload carries `300/500`, the returned body length is between 300 and 500 characters, and no unrelated generated data is left behind.

- [ ] **Step 5: Record evidence.**

Report commit, test counts, deployed services, and the measured production body length. Do not record credentials, tokens, provider keys, or private reference contents.
