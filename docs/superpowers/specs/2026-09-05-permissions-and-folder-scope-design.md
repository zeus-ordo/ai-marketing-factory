# Permissions and Folder Scope Design

## Goal

修正正式環境的三項問題：

1. Manager 無法進入審核中心。
2. Company admin 無法調整成員角色／權限。
3. Platform 建立的 folder 與實際知識資料沒有可靠關聯。

本設計不改變既有 Platform folder 的內容權限：Platform folder 與其內容對所有公司唯讀、可引用，但不可由 Company admin 或 Manager 修改、搬移、刪除。

## Scope Model

### Platform scope

- `company_id = NULL` 或等價的 platform scope。
- Platform admin 可建立、修改、刪除與管理內容。
- 所有公司可讀取、搜尋、選擇並引用。
- Company admin、Manager 與一般成員不可修改 Platform folder 或其中內容。

### Company scope

- `company_id = <company UUID>`。
- 同公司的成員依 permission 讀取或操作。
- Company admin 可建立、修改、刪除 folder 與內容。
- Manager 可讀取與引用；是否可上傳內容由明確的 folder/content permission 控制，不能由 role name 推斷。

## Permission Contract

新增並統一使用下列 permission：

- `review:manage`：讀取審核中心、查看診斷、執行核准／退回／要求修改。
- `member:assign_role`：在同一 company 內調整成員的 company roles。
- `folder:read`：讀取可見 Platform/company folders。
- `folder:create`：建立 company folder；Platform folder 仍只允許 platform admin。
- `folder:edit`：修改可操作 folder metadata。
- `folder:delete`：刪除可操作 folder；Platform folder 不可由 company scope 刪除。
- `folder:use`：在 campaign/reference/context 中引用可見 folder。

### Permission enforcement

- UI route guard、side navigation、API route、service authorization 使用同一 permission contract。
- 不使用 `manager`、`admin` 等 role name 作為唯一授權依據。
- `*` 與既有 platform-admin bypass 保持相容。
- 所有 company-scoped mutation 驗證 token company 與 target company 相同。
- Company role 不得指派 platform role，也不得修改另一 company 的 member/role/folder。

## Data Model

新增 additive migration：

```text
folders
- folder_id UUID/opaque id primary key
- company_id UUID nullable
- scope platform|company
- name text
- created_by UUID
- created_at timestamp
- updated_at timestamp

knowledge_items
- folder_id nullable foreign key
- company_id nullable/required according to existing ownership model

campaign_references
- folder_id nullable foreign key
- existing folder/category metadata retained during compatibility period
```

Constraints:

- Platform folder requires `company_id IS NULL`.
- Company folder requires `company_id IS NOT NULL`.
- Folder name uniqueness is scoped by `(scope, company_id, normalized_name)`.
- Existing `metadata.category`／文字 folder 仍可讀取，但新寫入一律保存 `folder_id`。

### Migration/backfill

1. 建立 folders 與 nullable `folder_id` columns，不刪除既有資料。
2. 將既有 persisted folder names 匯入 company 或 platform scope；無法判斷 owner 的資料先標記為 platform read-only，並寫 migration audit。
3. 以現有 `metadata.category`／campaign reference folder 名稱做 best-effort backfill。
4. 無法匹配的 item 保留 `folder_id=NULL`，顯示於 General/Unfiled，不阻塞登入或既有 campaign。
5. 新舊欄位並行一個相容週期後，才考慮移除文字 fallback。

## Work Packages and Order

### Phase 1 — Permission contract and Manager review access

- 定義 shared permission constants。
- 修正 Review page、side nav、review API/service guards。
- 確認 Manager role seed/default permissions 包含 `review:manage`。
- 加入 Manager、普通 member、platform admin 的 authorization tests。

### Phase 2 — Company admin member role editing

- 後端新增／採用 `member:assign_role` guard。
- 增加同 company、非 platform role、target member validation。
- Members UI 顯示角色編輯、多選與成功／失敗狀態。
- 呼叫既有 `PUT /companies/{company_id}/members/{member_id}/roles`。
- 寫 audit log，避免修改自己或跨 company。

### Phase 3 — Persistent folder and content association

- 新增 additive schema/migration 與 repository methods。
- 建立 platform/company folder API 與 scope-aware authorization。
- 將 knowledge item/reference upload、list、move、delete 改為 `folder_id`。
- Platform folder 只提供 read/use API；mutation 回傳 403。
- 更新 Content Studio、Campaign reference selector、Manager/Company admin UI。
- 加入 migration/backfill、ownership、visibility、引用與刪除測試。

### Phase 4 — Integration and rollout

- 執行 service/UI tests、API contract tests、lint、build。
- 在 staging 建立 platform/company folder、上傳內容、跨角色驗證。
- 備份 PostgreSQL，執行 additive migration。
- 部署後驗證 Manager review、Company admin role editing、folder read/use/mutation boundaries。
- 觀察 permission-denied、folder lookup、migration 與 audit log metrics。

## Acceptance Criteria

- Manager 登入後可進入 Review center，且只能操作其 permission 允許的 review actions。
- Company admin 可調整同公司成員的 company role；跨公司、platform role、未授權 action 均被拒絕。
- Platform admin 建立的 folder 與內容可被公司讀取與引用，但 company admin/Manager 的修改、刪除、搬移 API 回傳 403。
- Company folder 的內容只對同公司可見，且 folder 與 item/reference 關聯在重新部署後仍存在。
- 舊有 folder/category 資料可讀取；migration 不刪除 campaign/reference/knowledge item。
- UI 與 API 使用相同 permission contract，不再依賴 role name 字串。
- 所有 mutation 都有 audit event，且不記錄 secrets 或 raw credentials。

## Risks and Mitigations

- **既有 folder store 是 frontend local filesystem**：先做 additive backfill，再移除 local store；GCP deploy 前確認 volume/DB persistence。
- **Permission naming compatibility**：保留既有 `review:approve/reject/revision` 與 `member:manage` 的相容讀取，逐步導向新 permission。
- **Platform content exposure**：所有 read/use response 必須過 scope filter，mutation 明確拒絕 platform scope。
- **Migration ambiguity**：無法判斷 owner 的資料先以 platform read-only 處理並記錄 audit，不自動賦予 company 寫入權。
