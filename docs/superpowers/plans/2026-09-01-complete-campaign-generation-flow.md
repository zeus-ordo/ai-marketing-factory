# 完善建立活動與生成流程 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Campaign creation validate all business rules, assemble traceable internal and external references at an actual 75:25 budget, and execute generation tasks with reliable failure isolation and review visibility.

**Architecture:** Keep Campaign Service as the workflow owner. Add focused backend modules for validation, industry matching, external search, and context assembly; persist an immutable generation-context snapshot that every Worker task references. Keep the existing frontend workflow and APIs compatible while exposing validation, source, ratio, and task failure information.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, Psycopg/PostgreSQL, httpx, pytest; Next.js 16, React 19, TypeScript/TSX; Google Programmable Search API; existing Redis Streams orchestrator.

## Global Constraints

- The required fields are `campaign_name`, `product_name`, `objective`, `industry_category`, and `project_description`.
- When `deliverables.ads_strategy > 0`, `budget` must be finite and greater than zero.
- Source priority is user-selected Reference > immediate upload/campaign Reference > matching industry folder > other internal data > external web data.
- External web results must be labeled `external_web` and retain URL, title, summary, retrieved timestamp, query, and provider.
- The first Search Adapter provider is Google Programmable Search/Custom Search API.
- Internal and external context budgets are `floor(total_budget * 0.75)` and `total_budget - internal_budget`.
- Do not put API keys in Git, database records, prompts, or ordinary logs.
- A failed dependency becomes `blocked`; unrelated tasks continue; retryable failures use exponential backoff and a finite retry limit.
- Existing General, immediate-upload, custom-folder, and campaign-reference data remain compatible.
- Do not change existing Campaign Reference API contracts unless the new fields are additive and backward compatible.

---

## File Map

- `services/campaign_service/app/schemas.py`: strict request and response validation models.
- `services/campaign_service/app/validation.py`: reusable business validation rules.
- `services/campaign_service/app/industry_matching.py`: normalized industry synonyms and matching.
- `services/campaign_service/app/external_search.py`: provider protocol, Google adapter, normalized result model.
- `services/campaign_service/app/context_assembler.py`: source ranking, token/character budgeting, snapshot construction.
- `services/campaign_service/app/persistence.py`: generation-context and task-attempt persistence.
- `services/campaign_service/app/main.py`: integrate validation, context creation, task dispatch, retry/error endpoints.
- `services/orchestrator/app/main.py`: retry, blocked dependency, and task state transitions.
- `app/campaigns/page.tsx`: display validation/source/task status without changing the core form flow.
- `app/review/page.tsx` and `components/review/*`: show source and generation diagnostics.
- `deploy/docker-compose.gcp.yml`: pass search configuration without embedding secrets.
- `services/*/test_*.py` and `tests_e2e/*`: unit, integration, and E2E coverage.

---

### Task 1: Enforce Campaign business validation at the API boundary

**Files:**
- Create: `services/campaign_service/app/validation.py`
- Modify: `services/campaign_service/app/schemas.py`
- Modify: `services/campaign_service/app/main.py` at `create_campaign`
- Test: `services/campaign_service/test_campaign_validation.py`

**Interfaces:**
- Produces `validate_campaign_brief(brief: CampaignBrief) -> None` and raises `HTTPException(status_code=422, detail={"field": "must not be blank"})` for invalid input.
- `CampaignBrief` continues accepting existing aliases and valid old payloads.

- [ ] **Step 1: Write failing pytest cases**

Create tests covering each behavior:

```python
def test_rejects_blank_required_fields():
    with pytest.raises(HTTPException) as exc:
        validate_campaign_brief(valid_brief(industry_category="   "))
    assert exc.value.status_code == 422
    assert "industry_category" in str(exc.value.detail)


def test_requires_positive_budget_when_ads_are_selected():
    with pytest.raises(HTTPException) as exc:
        validate_campaign_brief(valid_brief(budget=0, ads_strategy=1))
    assert exc.value.status_code == 422
    assert "budget" in str(exc.value.detail)


def test_allows_zero_budget_without_ads_strategy():
    validate_campaign_brief(valid_brief(budget=0, ads_strategy=0))
```

- [ ] **Step 2: Run the focused tests and confirm RED**

Run:

```bash
pytest services/campaign_service/test_campaign_validation.py -q
```

Expected: FAIL because `validation.py` and `validate_campaign_brief` do not yet exist.

- [ ] **Step 3: Implement the validation function**

Trim and validate the five required string fields. Reject non-finite budgets and reject `budget <= 0` only when `ads_strategy > 0`. Keep Pydantic structural validation for types and use the business validator for blank strings and conditional rules.

- [ ] **Step 4: Integrate validation before persistence or dispatch**

Call `validate_campaign_brief(brief)` at the beginning of `create_campaign`, after JWT permission validation and before `store.create_campaign`. Ensure invalid requests create no Campaign, Run, Task, or trace event.

- [ ] **Step 5: Run tests and build**

Run:

```bash
pytest services/campaign_service/test_campaign_validation.py -q
npm run build
```

Expected: all focused tests pass and the frontend build succeeds.

- [ ] **Step 6: Commit**

```bash
git add services/campaign_service/app/validation.py services/campaign_service/app/schemas.py services/campaign_service/app/main.py services/campaign_service/test_campaign_validation.py
git commit -m "Enforce campaign creation business rules"
```

### Task 2: Add source tagging and industry matching

**Files:**
- Create: `services/campaign_service/app/industry_matching.py`
- Modify: `services/campaign_service/app/main.py` prompt/reference helpers
- Modify: `services/campaign_service/app/schemas.py` only for additive source metadata models
- Test: `services/campaign_service/test_industry_matching.py`

**Interfaces:**
- `normalize_industry(value: str) -> str`
- `industry_terms(value: str) -> set[str]`
- `match_industry_items(industry_category: str, product_name: str, objective: str, items: list[dict[str, Any]], limit: int = 8) -> list[dict[str, Any]]`
- Each selected item carries `source_type` from `user_selected`, `immediate_upload`, `campaign_reference`, or `industry_matched`.

- [ ] **Step 1: Write failing matcher tests**

```python
def test_matches_cantonese_restaurant_synonyms():
    items = [{"title": "調酒菜單", "description": "酒吧夜生活", "metadata": {"category": "餐酒館"}}]
    matched = match_industry_items("餐酒館", "新品調酒", "awareness", items)
    assert [item["title"] for item in matched] == ["調酒菜單"]


def test_does_not_match_unrelated_industry():
    items = [{"title": "汽車保養", "description": "車輛維修", "metadata": {"category": "汽車"}}]
    assert match_industry_items("餐酒館", "新品調酒", "awareness", items) == []
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```bash
pytest services/campaign_service/test_industry_matching.py -q
```

Expected: FAIL because the matcher module does not exist.

- [ ] **Step 3: Implement normalized terms and matching**

Include explicit synonym groups such as `餐酒館 -> 酒吧、調酒、餐飲、品酒、夜生活、餐廳`. Match folder/category, title, description, metadata keywords, product name, and objective. Rank exact industry match before synonym match and cap results at eight.

- [ ] **Step 4: Tag all context sources**

When building campaign context, tag user-selected Knowledge Items and campaign References before industry matching. Preserve raw IDs and folder names. Do not classify model knowledge as `external_web`.

- [ ] **Step 5: Run tests and commit**

```bash
pytest services/campaign_service/test_industry_matching.py -q
git add services/campaign_service/app/industry_matching.py services/campaign_service/app/main.py services/campaign_service/app/schemas.py services/campaign_service/test_industry_matching.py
git commit -m "Tag references and match industry knowledge"
```

### Task 3: Implement pluggable external Search Adapter with Google provider

**Files:**
- Create: `services/campaign_service/app/external_search.py`
- Modify: `services/campaign_service/requirements.txt` only if the existing `httpx` dependency is absent
- Modify: `services/campaign_service/app/main.py` configuration wiring
- Modify: `deploy/docker-compose.gcp.yml` with non-secret environment variable names
- Test: `services/campaign_service/test_external_search.py`

**Interfaces:**
- `ExternalSearchResult(source_type: Literal["external_web"], title: str, url: str, summary: str, retrieved_at: datetime, query: str, provider: str)`
- `class SearchProvider(Protocol): search(query: str, limit: int) -> list[ExternalSearchResult]`
- `GoogleCustomSearchProvider(api_key: str, engine_id: str, base_url: str = "https://www.googleapis.com/customsearch/v1")`
- `build_search_provider(settings) -> SearchProvider | None`

- [ ] **Step 1: Write failing adapter tests**

Use `httpx.MockTransport` to test the adapter without real network calls:

```python
def test_google_provider_normalizes_results():
    provider = GoogleCustomSearchProvider("key", "engine", client=mock_google_client())
    results = provider.search("新品調酒 餐酒館 awareness", 3)
    assert results[0].source_type == "external_web"
    assert results[0].url == "https://example.com/source"
    assert results[0].provider == "google"


def test_search_failure_is_classified_without_secret_leak():
    provider = GoogleCustomSearchProvider("key", "engine", client=failing_client())
    with pytest.raises(ExternalSearchError) as exc:
        provider.search("query", 3)
    assert "key" not in str(exc.value)
```

- [ ] **Step 2: Run tests and verify RED**

```bash
pytest services/campaign_service/test_external_search.py -q
```

Expected: FAIL because the provider and normalized result do not exist.

- [ ] **Step 3: Implement the provider and normalized error classes**

Send `key`, `cx`, `q`, and `num` to Google Custom Search. Normalize title, link, snippet, query, provider, and retrieval time. Classify HTTP 429 as `quota`, timeout as `timeout`, and other HTTP failures as `provider_error`; redact keys from all exception messages.

- [ ] **Step 4: Add configuration without storing secrets**

Support:

```text
EXTERNAL_SEARCH_PROVIDER=google
EXTERNAL_SEARCH_API_KEY=<secret>
EXTERNAL_SEARCH_ENGINE_ID=<engine-id>
```

Do not place values in `docker-compose.gcp.yml`, Git, database, prompt, or ordinary logs. If configuration is incomplete, return a classified `not_configured` status and allow internal-only generation.

- [ ] **Step 5: Build the automatic query**

Generate the query from `product_name + industry_category + objective`. Save the query with the normalized results. Do not accept user-entered search keywords in this version.

- [ ] **Step 6: Run tests and commit**

```bash
pytest services/campaign_service/test_external_search.py -q
git add services/campaign_service/app/external_search.py services/campaign_service/requirements.txt services/campaign_service/app/main.py deploy/docker-compose.gcp.yml services/campaign_service/test_external_search.py
git commit -m "Add pluggable Google web search adapter"
```

### Task 4: Assemble and persist measurable 75:25 generation Context

**Files:**
- Create: `services/campaign_service/app/context_assembler.py`
- Modify: `services/campaign_service/app/persistence.py` to create `generation_contexts` and `generation_context_items`
- Modify: `services/campaign_service/app/main.py` to create one snapshot before dispatch
- Test: `services/campaign_service/test_context_assembler.py`

**Interfaces:**
- `ContextSourceItem(source_type: str, source_id: str, label: str, text: str, metadata: dict[str, Any])`
- `GenerationContextSnapshot(generation_context_id: str, campaign_id: str, internal_token_count: int, external_token_count: int, internal_ratio: float, external_ratio: float, items: list[ContextSourceItem], external_source_urls: list[str])`
- `assemble_generation_context(campaign: CampaignRecord, selected_items: list[ContextSourceItem], industry_items: list[ContextSourceItem], external_items: list[ContextSourceItem], total_budget: int) -> GenerationContextSnapshot`

- [ ] **Step 1: Write failing budget tests**

```python
def test_allocates_internal_and_external_budgets():
    snapshot = assemble_generation_context(campaign, internal_items, industry_items, external_items, 1000)
    assert snapshot.internal_token_count <= 750
    assert snapshot.external_token_count <= 250
    assert snapshot.internal_ratio == pytest.approx(0.75, abs=0.02)
    assert snapshot.external_ratio == pytest.approx(0.25, abs=0.02)


def test_user_selected_items_beat_industry_and_external_items():
    snapshot = assemble_generation_context(campaign, selected_items, industry_items, external_items, 100)
    assert snapshot.items[0].source_type in {"user_selected", "immediate_upload", "campaign_reference"}


def test_internal_shortage_does_not_relabel_external_content():
    snapshot = assemble_generation_context(campaign, [], [], external_items, 100)
    assert all(item.source_type == "external_web" for item in snapshot.items)
```

- [ ] **Step 2: Run tests and verify RED**

```bash
pytest services/campaign_service/test_context_assembler.py -q
```

Expected: FAIL because the assembler and snapshot models do not exist.

- [ ] **Step 3: Implement source ranking and budget allocation**

Estimate tokens consistently using the existing tokenizer if available; otherwise use a documented UTF-8 character estimate. Allocate `floor(total_budget * 0.75)` to internal items and the remainder to external items. Keep activity basic fields outside the source ratio and record the exact counts used.

- [ ] **Step 4: Persist immutable snapshot records**

Create tables with additive schema initialization only. Store one snapshot per Campaign Run and one item row per included source. Store source IDs, folder names, URLs, provider, query, token estimates, and retrieval time. Never store raw API secrets.

- [ ] **Step 5: Use one snapshot for every Worker**

Create the snapshot before orchestrator dispatch. Build Copy/Image/Video/Ads payload prompts from the same snapshot. Include only source labels and content needed by the Worker; include `generation_context_id` in every task payload and asset metadata.

- [ ] **Step 6: Run tests and commit**

```bash
pytest services/campaign_service/test_context_assembler.py -q
pytest services/campaign_service/test_campaign_validation.py services/campaign_service/test_industry_matching.py services/campaign_service/test_external_search.py -q
git add services/campaign_service/app/context_assembler.py services/campaign_service/app/persistence.py services/campaign_service/app/main.py services/campaign_service/test_context_assembler.py
git commit -m "Persist measurable generation context"
```

### Task 5: Make Worker failures finite, isolated, and retryable

**Files:**
- Modify: `services/orchestrator/app/main.py`
- Modify: `services/campaign_service/app/main.py` result and task endpoints
- Modify: `services/campaign_service/app/persistence.py` task attempt fields/table
- Test: `services/orchestrator/test_task_failure_isolation.py`
- Test: `services/campaign_service/test_worker_result_state.py`

**Interfaces:**
- `classify_worker_error(exc: Exception) -> Literal["quota", "rate_limit", "timeout", "provider_error", "validation", "unknown"]`
- `next_retry_delay(attempt: int, base_seconds: float = 5.0, max_seconds: float = 300.0) -> float`
- Task states remain `pending`, `planned`, `running`, `retrying`, `passed`, `failed`, `blocked`.

- [ ] **Step 1: Write failing isolation tests**

```python
def test_image_failure_blocks_video_but_not_unrelated_copy():
    state = run_scenario(image_error="quota")
    assert state["image"].status == "failed"
    assert state["video"].status == "blocked"
    assert state["copy"].status == "passed"


def test_retry_delay_is_bounded():
    assert next_retry_delay(1) == 5.0
    assert next_retry_delay(20) == 300.0


def test_quota_failure_does_not_retry_forever():
    state = run_until_terminal_failure(error="quota")
    assert state.status == "failed"
    assert state.retry_count <= MAX_RETRY
```

- [ ] **Step 2: Run tests and verify RED**

```bash
pytest services/orchestrator/test_task_failure_isolation.py services/campaign_service/test_worker_result_state.py -q
```

Expected: FAIL because finite error classification and blocked transitions are not implemented.

- [ ] **Step 3: Implement error classification and backoff**

Map upstream HTTP 429 and quota-depleted messages to `quota`/`rate_limit`; map network timeouts to `timeout`; redact secrets from stored detail. Retry only retryable classes, with exponential backoff capped at 300 seconds and a finite maximum attempt count.

- [ ] **Step 4: Implement dependency transitions**

When a task reaches terminal `failed`, mark only pending descendants as `blocked` with `blocked_by_task_id` and `blocked_reason`. Continue unrelated ready tasks. Persist state before updating in-memory state.

- [ ] **Step 5: Add single-task retry support**

Add an additive internal/API operation that accepts a failed task ID, reuses the same Campaign Run context unless regeneration is explicitly requested, resets only that task and its blocked descendants, and publishes only ready tasks. Preserve previous attempts for audit.

- [ ] **Step 6: Run tests and commit**

```bash
pytest services/orchestrator/test_task_failure_isolation.py services/campaign_service/test_worker_result_state.py -q
git add services/orchestrator/app/main.py services/campaign_service/app/main.py services/campaign_service/app/persistence.py services/orchestrator/test_task_failure_isolation.py services/campaign_service/test_worker_result_state.py
git commit -m "Isolate worker failures and add bounded retries"
```

### Task 6: Expose validation, sources, ratios, and failures in the UI and review center

**Files:**
- Modify: `app/campaigns/page.tsx`
- Modify: `app/review/page.tsx`
- Modify: `components/review/review-queue-table.tsx`
- Modify: `lib/api/campaigns.ts`
- Modify: `lib/i18n/translations.ts`
- Test: `scripts/test-campaign-flow-contract.mjs`

**Interfaces:**
- Campaign API response additions are optional: `generation_context_id`, `source_summary`, and task error fields.
- Existing role behavior remains: `*`, `admin`, `platform:admin`, and review permissions can access Review Center.

- [ ] **Step 1: Write failing UI contract assertions**

The script must assert that the Campaign page displays backend validation errors, the Review page renders generation source/ratio fields, and the Campaign task view exposes a retry action for a failed task.

```js
const campaignPage = await readFile(new URL("../app/campaigns/page.tsx", import.meta.url), "utf8");
const reviewPage = await readFile(new URL("../app/review/page.tsx", import.meta.url), "utf8");
if (!campaignPage.includes("generation_context_id")) throw new Error("Campaign page must display generation_context_id");
if (!reviewPage.includes("internal_ratio")) throw new Error("Review page must display internal_ratio");
```

- [ ] **Step 2: Run the contract test and verify RED**

```bash
node scripts/test-campaign-flow-contract.mjs
```

Expected: FAIL because the new diagnostics are not rendered.

- [ ] **Step 3: Display clear create errors**

Show HTTP 422 field errors without clearing the form. Keep conditional budget guidance adjacent to the Ads selection. Do not allow the frontend to hide backend validation failures.

- [ ] **Step 4: Display generation diagnostics**

In Campaign and Review views show source type, selected file/folder, external URL, internal/external counts and ratios, task provider/model, status, retry count, and sanitized error reason.

- [ ] **Step 5: Add single-task retry UI**

Add a retry button only for terminal failed tasks. Disable it while busy and show the server response. Do not retry blocked descendants automatically unless the backend resets them as part of the same operation.

- [ ] **Step 6: Add translations and run checks**

Add English, Traditional Chinese, and Japanese labels for source types, ratio fields, quota errors, blocked tasks, and retry. Run:

```bash
node scripts/test-campaign-flow-contract.mjs
npm run build
```

- [ ] **Step 7: Commit**

```bash
git add app/campaigns/page.tsx app/review/page.tsx components/review/review-queue-table.tsx lib/api/campaigns.ts lib/i18n/translations.ts scripts/test-campaign-flow-contract.mjs
git commit -m "Expose generation diagnostics and task retry"
```

### Task 7: End-to-end verification and GCP rollout

**Files:**
- Create: `tests_e2e/test_complete_campaign_flow.py`
- Modify: `docs/release/uat-test-script.md`
- Modify: `docs/release/deployment-checklist.md`

**Interfaces:**
- Uses the existing public API and test accounts; does not print JWTs or provider keys.

- [ ] **Step 1: Add E2E tests for all acceptance criteria**

Cover:

1. Missing each required field returns HTTP 422 and creates no Campaign.
2. Ads without a positive budget returns HTTP 422.
3. Campaign with immediate-upload and industry references stores both source types.
4. Google adapter results are stored as `external_web` with URLs.
5. Generation snapshot reports measurable internal/external counts.
6. One Worker quota failure produces failed/blocked states without infinite retry.
7. Failed task retry resets only the intended branch.
8. Review Center shows diagnostics for an admin/company admin.

- [ ] **Step 2: Run local backend and frontend checks**

```bash
pytest services/campaign_service -q
pytest services/orchestrator -q
pytest tests_e2e/test_complete_campaign_flow.py -q
npm run build
```

- [ ] **Step 3: Configure GCP secrets out of band**

Create the Google Search API key and engine ID only in the VM secret file or secret manager integration. Set `EXTERNAL_SEARCH_PROVIDER=google` and verify logs show provider name only, never the key.

- [ ] **Step 4: Deploy in dependency order**

```bash
gcloud compute ssh ai-marketing-factory --zone=asia-east1-a --command="cd /opt/ai-marketing-factory && git pull origin master && cd deploy && docker compose -f docker-compose.gcp.yml up -d --build campaign-service orchestrator worker-copy worker-image worker-video worker-ads frontend"
```

- [ ] **Step 5: Run GCP smoke test**

Use the admin test account to create a temporary Campaign, upload/select a Reference, verify the source snapshot, observe task statuses, and clean up only the temporary Campaign. Verify all containers are `Up` and no secrets appear in logs.

- [ ] **Step 6: Update release documentation and commit**

```bash
git add tests_e2e/test_complete_campaign_flow.py docs/release/uat-test-script.md docs/release/deployment-checklist.md
git commit -m "Add complete campaign flow acceptance tests"
```

## Final Acceptance Checklist

- [ ] Frontend and backend both reject blank required fields.
- [ ] Ads selection requires a positive budget at both layers.
- [ ] User-selected and industry-matched internal sources are traceable.
- [ ] Google web results are traceable as external sources.
- [ ] Every Worker uses one immutable generation context snapshot.
- [ ] Actual source counts and ratios are recorded.
- [ ] Quota, rate-limit, timeout, and provider errors are classified.
- [ ] Failed dependencies become blocked instead of infinite pending.
- [ ] Unrelated Workers continue.
- [ ] Failed tasks can be retried individually.
- [ ] Review Center exposes source, ratio, provider, and failure data.
- [ ] GCP deployment and E2E smoke test pass without secret leakage.
