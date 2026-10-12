# Permissions and Folder Scope Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修正 Manager 審核權限、Company admin 成員角色編輯，並將 Platform/Company folders 與知識資料及 campaign references 建立持久化關聯。

**Architecture:** 先建立跨前後端一致的 permission contract；接著使用既有 member-role API 完成 company-scoped role assignment；最後把 frontend local folder store 遷移為 campaign-service persistence 的 scoped folder model，讓 platform folders read/use-only、company folders 可依 permission 管理。所有 migration additive，保留現有 category/folder fallback。

**Tech Stack:** FastAPI, PostgreSQL/psycopg, membership-service/asyncpg, Next.js 16, React, TypeScript, pytest, ESLint.

## Global Constraints

- Platform folders 與內容對所有公司可讀取、搜尋、選擇、引用，但 Company admin/Manager 不可修改、搬移、刪除。
- Company mutations 必須驗證 JWT `company_id` 與 target company 相同。
- Company role 不得指派 platform role，也不得跨 company 修改 member/role/folder。
- 保留 `*` 與既有 platform-admin bypass。
- Permission 判斷不得以 `manager`、`admin` 等 role name 作為唯一授權依據。
- 所有 schema migration 必須 additive；不得刪除既有 campaign/reference/knowledge data。
- 既有 `metadata.category` 與文字 folder 在相容期間保留為 read fallback；新寫入必須保存 `folder_id`。
- 所有 mutation 寫入 audit event，不記錄 secrets、token、authorization header 或 raw provider response。
- Platform folders 的 mutation 必須回傳 HTTP 403；不可透過前端隱藏按鈕取代後端授權。

---

## Task 1: Shared permission contract and Manager review access

**Files:**
- Create: `services/membership_service/app/permissions.py`
- Modify: `services/membership_service/app/routes/company.py`
- Modify: `services/membership_service/app/routes/roles.py`
- Modify: `services/membership_service/app/main.py` (startup additive role/permission compatibility seed)
- Modify: `services/campaign_service/app/main.py:require_review_action_access`, review list/action authorization helpers
- Modify: `app/review/page.tsx`
- Modify: `components/layout/side-nav-bar.tsx`
- Modify: `lib/auth/permissions.ts` (create if no shared frontend helper exists)
- Test: `services/membership_service/test_permissions.py`
- Test: `services/campaign_service/test_review_permissions.py`
- Test: `scripts/test-campaign-flow-contract.mjs` or an additive permission contract test

**Interfaces:**
- Produces canonical permission names: `review:manage`, `member:assign_role`, `folder:read`, `folder:create`, `folder:edit`, `folder:delete`, `folder:use`.
- `review:manage` grants review queue read plus approve/reject/revision operations, while existing granular review permissions remain accepted during migration.
- Frontend helper `hasPermission(permissions, required)` accepts `*`, exact permissions, and the existing compatibility aliases without checking role names.

- [ ] **Step 1: Write failing permission tests.**

Add tests proving a JWT with `review:manage` can list review items and access the Review page contract, a JWT without review permissions is denied, and a JWT with `member:manage` but without `member:assign_role` cannot update another member's roles. Add assertions that platform/admin bypass still works.

- [ ] **Step 2: Run the focused tests and verify expected failures.**

Run:

```bash
python -m pytest services/membership_service/test_permissions.py services/campaign_service/test_review_permissions.py -q
```

Expected: failures because the new permissions are not yet recognized by route guards and frontend permission contracts.

- [ ] **Step 3: Add canonical permission constants and compatibility helpers.**

Define one Python set/list used by role validation and one TypeScript helper used by Review, side navigation, Members, and Roles pages. Keep existing `review:approve`, `review:reject`, `review:revision`, and `member:manage` as compatibility permissions, but make new code prefer `review:manage` and `member:assign_role`.

- [ ] **Step 4: Update Manager review authorization.**

Update campaign-service review list/action guards to accept `review:manage` and retain the existing granular permissions. Update `app/review/page.tsx` and `components/layout/side-nav-bar.tsx` to use the helper. Ensure `review:manage` permits diagnostics/read access and configured review actions, but does not grant platform administration.

- [ ] **Step 5: Update role validation and role seed/defaults.**

Add the new permissions to membership-service allowed permissions and ensure the Manager default/company role receives `review:manage` only for review work. Do not grant `member:assign_role` to Manager by default. Ensure role update validation rejects unknown permission names and platform roles remain non-assignable.

- [ ] **Step 6: Run focused tests and commit.**

Run the focused pytest commands, campaign HTTP route tests, and frontend contract checks. Commit only Task 1 files:

```bash
git add services/membership_service services/campaign_service app/review components/review components/layout lib/auth scripts
git commit -m "Unify review and member permission contract"
```

Expected: permission tests pass; existing review and authentication suites remain green.

---

## Task 2: Company admin member role editing

**Files:**
- Modify: `services/membership_service/app/routes/company.py`
- Modify: `services/membership_service/app/repositories/role.py`
- Modify: `services/membership_service/app/repositories/member.py`
- Modify: `services/membership_service/app/routes/roles.py` if role listing must accept `member:assign_role`
- Modify: `lib/api/auth.ts`
- Modify: `app/members/page.tsx`
- Modify: `lib/i18n/translations.ts`
- Test: `services/membership_service/test_company_member_roles.py`
- Test: `services/membership_service/test_routes.py` or the existing membership route test location
- Test: `scripts/test-member-role-contract.mjs` (create if no equivalent UI contract exists)

**Interfaces:**
- Existing API remains `PUT /api/v1/companies/{company_id}/members/{member_id}/roles` with `{ "role_ids": string[] }`.
- The endpoint requires `member:assign_role` or the compatibility `member:manage`, validates same-company target/member, rejects platform roles, and returns `{ "message": "Roles updated" }`.
- Members UI uses `updateMemberRoles(companyId, memberId, roleIds)` and only renders the editor when the permission helper allows it.

- [ ] **Step 1: Write failing backend tests.**

Cover: same-company role assignment succeeds; cross-company target returns 403; platform role ID returns 403/400; unknown role ID returns 404/422; manager without `member:assign_role` cannot assign; company admin with the new permission can assign; self-edit policy is explicit and rejects editing the current member if that is the configured safety rule.

- [ ] **Step 2: Run tests to verify they fail for the missing permission/UI behavior.**

Run:

```bash
python -m pytest services/membership_service/test_company_member_roles.py -q
```

Expected: failures for the new permission and edge-case assertions.

- [ ] **Step 3: Harden the existing role assignment endpoint.**

Use the shared permission helper, fetch all requested roles in one repository operation, verify each role belongs to the target company and is not `is_system`/platform-scoped, then update member-role links transactionally. Emit an audit record containing actor/member/role IDs and result, never passwords or tokens.

- [ ] **Step 4: Add Members UI role editor.**

Load members and assignable company roles independently so a missing `role:manage` permission does not hide roles needed for assignment. Add a per-member multi-select, save/cancel state, loading/error feedback, and refresh the member row after success. Do not expose platform roles. Prevent editing the current admin account if the backend policy rejects self-edit.

- [ ] **Step 5: Add localized labels and behavior contract.**

Add English, Traditional Chinese, and Japanese strings for edit roles, save, cancel, forbidden platform role, and update failure. Add a contract test that asserts the editor calls the existing update API and is permission-gated.

- [ ] **Step 6: Run tests and commit.**

Run membership tests, frontend lint/build, and API route contract tests. Commit:

```bash
git add services/membership_service lib/api/auth.ts app/members lib/i18n scripts
git commit -m "Allow company admins to assign member roles"
```

---

## Task 3: Persistent scoped folders and content association

**Files:**
- Modify: `services/campaign_service/app/persistence.py` (additive `folders` table and `folder_id` columns)
- Modify: `services/campaign_service/app/main.py` (folder/reference/knowledge APIs and scope authorization)
- Modify: `services/campaign_service/app/store.py` if in-memory fallback needs scoped folders
- Modify: `services/campaign_service/app/schemas.py`
- Modify: `lib/api/campaigns.ts`
- Modify: `app/api/folders/route.ts`
- Modify: `app/api/folders/[name]/route.ts` (replace local-store behavior with authenticated backend proxy or remove after migration)
- Delete or deprecate: `lib/server/folders-store.ts` only after backend folder API is live and migration tests pass
- Modify: `app/content-studio/page.tsx`
- Modify: `app/campaigns/page.tsx`
- Modify: `lib/i18n/translations.ts`
- Test: `services/campaign_service/test_folder_scope.py`
- Test: `services/campaign_service/test_reference_folder_association.py`
- Test: `services/campaign_service/test_persistence_migrations.py`
- Test: `scripts/test-folder-scope-contract.mjs`

**Interfaces:**
- Backend folder endpoints use authenticated company scope and expose `folder_id`, `scope`, `company_id`, `name`, and timestamps.
- Platform read/use is available to authenticated companies; platform create/edit/delete requires platform-admin/internal authorization.
- Company create/edit/delete requires the corresponding `folder:*` permission and same-company ownership.
- New upload/update payloads accept `folder_id`; legacy `category`/folder text remains read-compatible during migration.

- [ ] **Step 1: Write failing migration and scope tests.**

Cover table creation on an existing database, platform/company uniqueness, platform read from a company JWT, company isolation, platform mutation rejection for company users, and null-folder fallback for legacy items. Add a test that a knowledge item and campaign reference preserve their folder after persistence reload.

- [ ] **Step 2: Run migration/scope tests to verify the missing table and authorization failures.**

Run:

```bash
python -m pytest services/campaign_service/test_folder_scope.py services/campaign_service/test_reference_folder_association.py services/campaign_service/test_persistence_migrations.py -q
```

Expected: failures because the folders table, folder IDs, and scoped API are not implemented.

- [ ] **Step 3: Add additive persistence schema and repository methods.**

Create `folders` with the platform/company constraints and normalized scoped uniqueness. Add nullable `folder_id` to knowledge and campaign-reference persistence. Implement list/get/create/update/delete methods with scope filters and transaction-safe foreign-key checks. Backfill existing text categories where a unique folder can be inferred; otherwise keep `folder_id=NULL` and return `General/Unfiled`.

- [ ] **Step 4: Implement scope-aware folder and content APIs.**

Replace the Next.js filesystem folder store as the source of truth. Add authenticated backend list/create/update/delete routes, enforce platform read/use-only for company users, and route knowledge/reference upload and move operations through `folder_id`. Keep legacy category in response for existing clients until the compatibility window ends.

- [ ] **Step 5: Update UI and folder visibility.**

Content Studio and Campaign reference selectors must display both platform and company folders, mark platform folders as read-only, disable mutation controls accordingly, and associate uploaded items with the selected `folder_id`. Add empty/unfiled handling and refresh after upload/move/delete. Ensure Manager can read/use but cannot mutate platform folders.

- [ ] **Step 6: Add migration/backfill and permission integration tests.**

Test Platform admin create/edit/delete, company read/use, company mutation of company folders, cross-company rejection, content persistence after process restart, and folder visibility through Review/Campaign context assembly. Add API contract assertions for 403 on platform mutations.

- [ ] **Step 7: Run full folder checks and commit.**

Run migration, campaign-service, membership permission, E2E folder, lint, build, secret scan, and diff checks. Commit:

```bash
git add services/campaign_service services/membership_service app/api/folders app/content-studio app/campaigns lib/api/campaigns lib/server lib/i18n scripts
git commit -m "Persist scoped folders and content associations"
```

---

## Task 4: Staging rollout and production verification

**Files:**
- Modify: `docs/release/deployment-checklist.md`
- Modify: `docs/release/complete-campaign-flow-runbook.md`
- Test: `tests_e2e/test_permissions_and_folder_scope.py`

- [ ] **Step 1: Add deterministic end-to-end coverage.**

Use ASGI/TestClient with mocked email/provider boundaries to verify Manager review access, Company admin role assignment, Platform read/use-only folder behavior, Company folder isolation, and restart persistence without live secrets.

- [ ] **Step 2: Run the complete offline gate.**

Run:

```bash
python -m pytest tests_e2e/test_permissions_and_folder_scope.py -q
python -m pytest services/membership_service services/campaign_service -q
npm run lint
npm run build
npm run check:secrets
```

- [ ] **Step 3: Prepare production migration.**

Create a Cloud SQL backup, run the additive migration, verify folders/folder IDs and existing reference counts, then deploy services. Do not delete the frontend local folder file until the persisted backend data and reads have been verified.

- [ ] **Step 4: Run post-deployment checks.**

Verify with separate accounts:

1. Manager can enter Review and cannot mutate Platform folders.
2. Company admin can edit same-company member roles but cannot assign Platform roles or cross-company roles.
3. Platform admin can manage Platform folders.
4. Company folder and content survive service restart and remain company-scoped.

- [ ] **Step 5: Commit release documentation.**

```bash
git add docs/release tests_e2e
git commit -m "Add permission and folder scope rollout checks"
```

## Final Verification Checklist

- [ ] Manager Review route and API permission tests pass.
- [ ] Company member role assignment tests pass, including cross-company/platform-role rejection.
- [ ] Folder migration/backfill tests pass on an existing database fixture.
- [ ] Platform folders are read/use-only for company users.
- [ ] Company folders and associated knowledge/reference records survive restart.
- [ ] Offline E2E, service tests, lint, build, secret scan pass.
- [ ] Cloud SQL backup exists before production migration.
- [ ] Production smoke tests pass with Manager, Company admin, and Platform admin accounts.
