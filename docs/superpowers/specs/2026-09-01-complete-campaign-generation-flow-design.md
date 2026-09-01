# 完善建立活動與生成流程設計規格

## 1. 背景

目前建立活動流程已具備部分前端欄位檢查、Reference 選擇與 Worker 分派，
但部分規則只存在於前端或 prompt 文字中：

- 後端未完整阻擋空白的產業類別與專案需求。
- 75:25 目前是提示詞要求，沒有實際計算與記錄。
- 產業資料匹配主要依簡單文字包含比對。
- Worker 限流或失敗可能使依賴任務長時間 pending。

本規格將建立可驗證、可追蹤且具失敗隔離能力的完整流程。

## 2. 目標

1. 前端與後端都強制驗證五個建立活動必填欄位。
2. 勾選投放策略時，預算必須大於零。
3. 使用者指定的 Reference 與對應產業資料優先於外部資料。
4. 系統自動依活動內容搜尋公開網路資料。
5. 內部資料與外部資料實際按約 75:25 組成生成 Context。
6. 保存每次生成使用的資料來源、token 數與比例。
7. 產業匹配支援資料夾、標題、描述及同義詞／關鍵字。
8. 單一 Worker 失敗不會讓整個活動無限卡住。
9. 支援 429、quota、timeout 的分類、退避重試與單一 Task 重試。
10. 審核中心可查看完整生成來源與錯誤資訊。

## 3. 非目標

- 本階段不更換既有 AI Provider。
- 本階段不重新設計整個 Campaign UI。
- 不把外部資料視為可信事實；外部內容必須保存來源 URL 與擷取時間。
- 不刪除既有 Reference 或 Knowledge Item。

## 4. 完整使用流程

```text
填寫活動表單
  ↓
前端驗證必填欄位與預算
  ↓
後端再次驗證相同規則
  ↓
選擇／上傳 Reference
  ↓
標記使用者資料來源
  ↓
標準化產業類別與同義詞
  ↓
匹配產業資料夾內容
  ↓
依產品、產業、目標自動搜尋公開網路
  ↓
組裝 75% 內部資料 + 25% 外部資料
  ↓
保存 Generation Context snapshot
  ↓
建立並分派各類 Worker Task
  ↓
個別重試／失敗隔離／依賴解除
  ↓
保存輸出與來源紀錄
  ↓
送入審核中心
  ↓
審核通過後發布
```

## 5. 活動欄位驗證

### 5.1 必填欄位

以下欄位必須是非空白字串：

- `campaign_name`：專案名稱
- `product_name`：品牌／產品名稱
- `objective`：活動目標
- `industry_category`：產業類別
- `project_description`：專案需求

前端在送出前顯示缺少欄位；後端 API 以 trim 後的值再次驗證，失敗回傳
HTTP 422，且不得建立 Campaign、Run 或 Task。

### 5.2 投放策略預算

當 `deliverables.ads_strategy > 0` 時，`budget` 必須是有限且大於零的數字。
前後端皆須驗證。未勾選投放策略時，預算依現有產品規則處理，但不得產生
負數或 NaN。

## 6. Reference 與資料來源分層

### 6.1 來源類型

每筆生成 Context item 必須有來源類型：

- `user_selected`：使用者從資料夾或檔案選取
- `immediate_upload`：Campaign 流程中的「即時上傳」
- `campaign_reference`：已掛到活動的手動 Reference
- `industry_matched`：依產業匹配的內部 Knowledge Item
- `external_web`：自動網路搜尋結果

### 6.2 優先順序

```text
使用者指定 Reference
> 即時上傳／活動 Reference
> 對應產業資料夾
> 其他內部資料
> 外部網路資料
```

使用者指定內容與外部資料衝突時，以使用者指定內容為準；系統仍需保留
衝突與來源紀錄。

## 7. 產業匹配

產業匹配器輸入：

- `industry_category`
- `product_name`
- `objective`

比對範圍：

- 資料夾名稱
- Knowledge Item 標題
- Knowledge Item 描述
- metadata 關鍵字

匹配方式依序為：

1. 完整名稱匹配
2. 同義詞／關鍵字匹配
3. 產品與活動目標的關聯詞匹配

例如 `餐酒館` 可對應：

```text
酒吧、調酒、餐飲、品酒、夜生活、餐廳
```

匹配結果最多取設定的上限，並記錄實際採用的資料夾與項目 ID。

## 8. 外部網路搜尋

系統自動使用以下欄位產生搜尋查詢：

```text
品牌／產品 + 產業類別 + 活動目標
```

外部結果必須保存：

- `url`
- `title`
- `summary`
- `retrieved_at`
- `query`

外部搜尋失敗時，不阻止內部資料生成，但記錄：

```text
external_search_status = failed
external_search_error = <分類後的錯誤>
```

不可將模型既有知識標記成已搜尋的外部資料。

## 9. 75:25 Context 組裝

Context 組裝器先設定 token budget，再依優先順序填入資料：

```text
internal_budget = floor(total_budget * 0.75)
external_budget = total_budget - internal_budget
```

內部資料不足時，剩餘空間不得自動把外部資料提升為內部資料；應記錄實際
比例，例如 `internal_ratio = 0.62`、`external_ratio = 0.25`、其餘為活動
基本資料。比例應以實際 token／字元估算值保存，並允許因內容邊界產生小幅
誤差。

每次生成保存一份 immutable snapshot，至少包含：

- `generation_context_id`
- `campaign_id`
- `task_id`
- `internal_token_count`
- `external_token_count`
- `internal_ratio`
- `external_ratio`
- `selected_reference_ids`
- `matched_folder_names`
- `external_source_urls`
- `created_at`

每個 Worker 使用相同 snapshot 的相關內容，不能各自重新搜尋造成來源不一致。

## 10. Task 執行與失敗隔離

Task 狀態至少包含：

```text
pending, planned, running, retrying, passed, failed, blocked
```

每個 Task 保存：

- 最後錯誤分類
- 最後錯誤訊息（去除 secret）
- 重試次數
- 下次重試時間
- provider／model
- generation_context_id

429、quota、timeout 使用 exponential backoff，達到上限後設為 `failed`，
不得無限 pending。

依賴 Task 的行為：

- 依賴成功：正常解除並執行
- 依賴失敗：設為 `blocked`，明確顯示阻塞原因
- 不相關 Task：可繼續執行，不因其他 Worker 失敗而停止

UI 提供單一失敗 Task 的重新執行功能，不必重跑整個 Campaign。

## 11. 審核中心

審核人員可查看：

- Campaign Brief
- 生成資產
- 使用者 Reference
- 對應產業資料夾與 Knowledge Item
- 外部搜尋來源 URL
- 實際內外部 token 比例
- 每個 Task 的狀態與錯誤
- Retry／quota／timeout 紀錄

具有 `*`、`admin`、`platform:admin` 或 review 相關權限者可進入審核中心；
其他角色維持無法進入。

## 12. 驗證標準

### 功能測試

- 缺任一必填欄位時，前後端皆拒絕建立。
- Ads 勾選且預算為零時，前後端皆拒絕建立。
- 使用者 Reference 確實出現在 snapshot 與 Worker context。
- 產業匹配結果可追蹤到資料夾與 item ID。
- 外部搜尋成功時保存 URL 與摘要。
- Context 實際比例符合設定並可查詢。
- Image 429 時，Image 為 failed、Video／Ads 為 blocked 或依獨立依賴規則處理。
- 失敗 Task 可單獨重試。
- 審核中心可查看來源與錯誤。

### 安全與可靠性測試

- Log 與 metadata 不得包含 API key、JWT 或 password。
- 外部內容必須標示為 `external_web`。
- Worker 失敗不得造成無限 retry。
- 既有 General／即時上傳／自訂資料夾資料維持相容。

## 13. 分階段交付

1. **Phase 1：後端驗證與錯誤模型**
2. **Phase 2：Reference source tagging 與產業匹配**
3. **Phase 3：外部搜尋 adapter 與來源保存**
4. **Phase 4：Context assembler 與 75:25 snapshot**
5. **Phase 5：Task retry、blocked、單一重試**
6. **Phase 6：審核中心資料來源呈現與完整 E2E 驗證**
