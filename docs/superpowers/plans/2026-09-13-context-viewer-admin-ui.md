# Context Viewer Admin UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 將獨立 Context Viewer 改造成非工程背景管理者可用的 AI 活動索引與活動紀錄介面。

**Architecture:** 保留現有 Next.js API、PostgreSQL query、session 與 redaction，不改動原 frontend 或 payload capture。將現有單頁拆成可理解的索引工作台與活動紀錄詳細區，透過 Campaign、日期／狀態、內容類型三種管理者索引找到紀錄，再以「要求 AI 做什麼／提供什麼資料／AI 回傳什麼」呈現內容。

**Tech Stack:** Next.js 16.3.5、React 19、TypeScript、Node test runner、現有 `pg` API。

## Global Constraints

- 使用者是系統管理者、營運或行銷管理者，不假設理解 JSON、payload、run 或 generation context。
- 以 Campaign／日期／內容類型作為主要索引；技術 ID 僅作為進階資訊。
- 不改變既有資料捕捉、權限、redaction 或 API 契約。
- 不新增自然語言搜尋、PostgreSQL schema、一般會員權限模型或 LLM 結果編輯器。
- 完整 prompt、來源與既有技術細節仍可查看、複製與下載，並維持 secret redaction。
- 保留鍵盤可用性、窄螢幕可讀性與清楚的 hover/focus/selected 狀態。
- 不將 Context Viewer 整合回原 frontend navigation。

---

### Task 1: 建立管理者活動索引資料與篩選模型

**Files:**
- Modify: `context-viewer/lib/query.ts`
- Modify: `context-viewer/app/api/contexts/route.ts`
- Modify: `context-viewer/test/query.test.ts`

**Interfaces:**
- `Filters` 新增可選 `activityType?: string`、`status?: string`、`from?: string`、`to?: string`，保留現有 `campaignId`、`generationContextId`、`runId`、`limit`、`offset`。
- `buildContextListQuery(filters)` 仍回傳 `{ text: string; values: unknown[] }`，新增條件一律使用 parameterized values。
- API `/api/contexts` 維持 JSON list response，為每筆提供管理者摘要所需的 `campaign_id`、`created_at`、`payload_count`、`context_item_count`、可推導的 activity type/status 欄位；不回傳未 redacted prompt。

- [ ] **Step 1: Write failing query tests**

在 `context-viewer/test/query.test.ts` 新增測試，驗證 activity type、status 與日期條件出現在 SQL predicate、值位於 `query.values`，且輸入不會直接插入 query text：

```ts
test("buildContextListQuery parameterizes administrator activity filters", () => {
  const query = buildContextListQuery({
    campaignId: "spring-launch",
    activityType: "copywriting",
    status: "completed",
    from: "2026-09-01",
    to: "2026-09-30",
  });

  assert.match(query.text, /created_at/);
  assert.match(query.text, /task_type|activity_type/);
  assert.ok(!query.text.includes("spring-launch"));
  assert.ok(query.values.includes("copywriting"));
  assert.ok(query.values.includes("completed"));
});
```

- [ ] **Step 2: Run the focused test and verify RED**

Run: `npm test -- --test-name-pattern="administrator activity filters"`

Expected: FAIL because `Filters` and `buildContextListQuery` do not yet include the new conditions.

- [ ] **Step 3: Implement the minimal query/API change**

Add only the new filters supported by persisted data. Use a fixed allowlist for activity type/status columns or expressions; never interpolate user-provided column names. Normalize empty values to undefined, keep the existing page cap of 100, and map database rows to stable JSON fields in the route.

- [ ] **Step 4: Run focused and existing viewer tests**

Run: `npm test`

Expected: all existing tests plus the new administrator filter test pass.

- [ ] **Step 5: Commit**

```bash
git add context-viewer/lib/query.ts context-viewer/app/api/contexts/route.ts context-viewer/test/query.test.ts
git commit -m "Add administrator activity filters"
```

### Task 2: Build the Campaign activity workbench

**Files:**
- Modify: `context-viewer/app/page.tsx`
- Modify: `context-viewer/app/globals.css` or create it if the current app has no global stylesheet
- Modify: `context-viewer/test/query.test.ts`

**Interfaces:**
- The page consumes `/api/campaigns` and `/api/contexts` using the existing session-aware request helper.
- Filter state includes campaign, date range, activity type, status, and optional advanced identifiers.
- Selecting a row calls the existing `/api/contexts/[generationContextId]` detail route and keeps the selected campaign/filter state visible.

- [ ] **Step 1: Add a failing page-structure test**

Extend the existing page source test to require the management labels and controls: `AI activity`, `Campaign`, `Date`, `Content type`, `Status`, `Clear filters`, `No AI activity found`, and `Next step`.

- [ ] **Step 2: Run the focused test and verify RED**

Run: `npm test -- --test-name-pattern="management|activity|filters"`

Expected: FAIL because the current page only exposes Campaigns, technical Filters, and a raw generation context table.

- [ ] **Step 3: Implement the accessible workbench layout**

Replace the raw filter/table presentation with:

1. A header naming the tool and signed-in administrator action.
2. A search/select control for Campaign.
3. Date-from/date-to controls, content type select, and human-readable status select.
4. Apply and Clear filters actions.
5. A list of activity cards or rows showing campaign name, activity type, translated status, timestamp, reference count, and output count.
6. Empty, loading, and error states with plain-language messages.

Use semantic labels and buttons rather than click-only table rows. Keep the advanced generation context ID/run ID fields in a collapsed “Technical details” section. Do not remove the existing API call behavior or expose raw secrets.

- [ ] **Step 4: Run viewer tests and production build**

Run:

```bash
npm test
npm run build
```

Expected: tests pass and Next production build completes without modifying the original frontend build scope.

- [ ] **Step 5: Commit**

```bash
git add context-viewer/app/page.tsx context-viewer/app/globals.css context-viewer/test/query.test.ts
git commit -m "Create administrator activity workbench"
```

### Task 3: Redesign the activity record detail view

**Files:**
- Modify: `context-viewer/app/page.tsx`
- Modify: `context-viewer/app/globals.css`
- Modify: `context-viewer/test/query.test.ts`

**Interfaces:**
- Detail data remains the existing `Detail` response and redacted payloads.
- Detail sections expose copy/text/JSON download actions without changing filenames or redaction semantics.

- [ ] **Step 1: Add failing detail-view assertions**

Require the page source to contain these user-facing sections and actions:

```ts
for (const label of [
  "What we asked the AI to do",
  "Information given to the AI",
  "What the AI returned",
  "Copy instruction",
  "View all information",
  "Technical details",
]) {
  assert.match(page, new RegExp(label));
}
```

- [ ] **Step 2: Run the test and verify RED**

Run: `npm test -- --test-name-pattern="detail|AI"`

Expected: FAIL because the current detail view uses engineering-oriented headings such as `Prompts`, `Persisted worker context payload`, and `Assembled generation context items`.

- [ ] **Step 3: Implement the activity record presentation**

Add a prominent record header with campaign name, activity type, date/time, and translated status. Add summary cards for requested output, information used, generated result count, and model response status. Render the three main sections in order:

1. Human-readable explanation and full prompt in a readable code-like panel.
2. Source/context list with labels and counts, with the full existing JSON available behind “View all information”.
3. Result summary with a clear next action and existing detail/download controls.

Place generation context ID, run ID, task ID, model, ratios, token counts, search state, and raw JSON under a collapsed technical section. Keep `internal_token_count` and `external_token_count` visible as metadata; run all displayed values through the existing redaction function.

- [ ] **Step 4: Add responsive and interaction states**

Ensure the detail view becomes one column below 760px, preserves focus outlines, supports keyboard activation, and shows copy/download failure feedback without throwing. Add a Back to activity list action that serializes the current campaign, date, type, and status filters into the list URL so they are restored on return.

- [ ] **Step 5: Run all viewer checks**

Run:

```bash
npm test
npm run build
```

Expected: all tests pass and production build completes.

- [ ] **Step 6: Commit**

```bash
git add context-viewer/app/page.tsx context-viewer/app/globals.css context-viewer/test/query.test.ts
git commit -m "Present readable LLM activity records"
```

### Task 4: Visual and deployment validation

**Files:**
- Modify: `docs/release/deployment-checklist.md` only if the final UI verification steps need recording
- Test: existing Context Viewer tests plus remote smoke checks

- [ ] **Step 1: Run the complete local validation set**

Run:

```bash
npm test
npm run build
python -m pytest services/campaign_service -q
python -m pytest services/orchestrator -q
git diff --check
```

Expected: viewer tests/build and both Python service suites pass; only documented deprecation/multiple-lockfile warnings may remain.

- [ ] **Step 2: Review the interface at the deployed-sized viewport**

Check desktop and narrow-screen layouts for readable hierarchy, visible filter state, empty/error states, focus indication, and no accidental raw secret/credential output.

- [ ] **Step 3: Deploy only after approval of the final UI**

Use the existing controlled deployment procedure. The UI-only change should rebuild `context-viewer`; do not alter PostgreSQL exposure or the original frontend service.

- [ ] **Step 4: Run remote smoke tests**

Verify the public viewer root returns `200`, unauthenticated API requests return `401`, login sets a session cookie, authenticated campaign/activity list returns `200`, and the original frontend remains available.

- [ ] **Step 5: Commit deployment evidence**

Record the deployed commit, service status, smoke-test results, and any historical-data limitation in the existing release/task report without recording passwords, session secrets, database URLs, or API keys.
