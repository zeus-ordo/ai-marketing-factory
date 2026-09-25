# Context Viewer 管理者介面設計規格

## 目標

將獨立 Context Viewer 從工程師導向的 context 查詢工具，調整為非工程背景管理者也能理解的 AI 活動紀錄工具。核心任務是讓管理者快速回答：

1. 哪一個 Campaign 發生了 AI 活動？
2. 何時執行、目前狀態與內容類型為何？
3. 這次實際送給 LLM 什麼指令？
4. 提供了哪些資料與參考來源？
5. AI 回傳了什麼結果？

不改變既有資料捕捉、權限、redaction 或 API 契約；本次只調整 Context Viewer 的資訊架構、文字語言與視覺呈現。

## 使用者與設計原則

- 使用者是系統管理者、營運或行銷管理者，不假設理解 JSON、payload、run 或 generation context。
- 以 Campaign／日期／內容類型作為主要索引；技術 ID 僅作為進階資訊。
- 先摘要、後細節；先顯示人類可讀的活動描述，再提供完整原文。
- 使用清楚的狀態文字：已完成、處理中、需要審核、失敗；避免只顯示資料庫 status。
- 不隱藏完整 prompt，但在畫面、copy 與 download 流程中維持既有 secret redaction。
- 保留鍵盤可用性、窄螢幕可讀性與清楚的 hover/focus/selected 狀態。

## 資訊架構

### 首頁：AI 活動索引

首頁採單一工作台布局，提供三種主要索引條件：

- Campaign：活動名稱或 Campaign ID 搜尋／選擇
- 日期與狀態：日期範圍、已完成／處理中／需要審核／失敗
- 內容類型：文案、圖片、影片、廣告策略

列表每筆以人類可讀摘要呈現：

```text
Spring launch
文案生成 · 已完成 · 2026/09/12 10:42
使用 12 份參考資料 · 產生 3 個草稿
```

空狀態需說明目前沒有符合條件的 AI 活動，並提供清除篩選操作。載入與 API error 狀態需有可理解的訊息，不顯示 stack trace。

### 詳細頁：活動紀錄

採用活動紀錄布局，右側或主要內容區依序展示：

1. **這次要求 AI 做什麼**：完整、可閱讀的 prompt／instruction，提供 Copy instruction。
2. **提供給 AI 的資料**：品牌設定、選用參考資料、既有活動 context 等摘要；提供 View all information。
3. **AI 回傳了什麼**：結果數量、結果狀態與進入產出內容的入口。
4. **技術詳細資訊**：可折疊或次要區域，包含 generation context ID、run ID、task ID、model 與完整 JSON 操作，不干擾一般閱讀。

每個區段可保留既有 copy、text download、JSON download，但按鈕文字以人類語言描述。Metadata 仍需顯示 token count、來源、搜尋狀態等有助於管理者判斷的資訊。

## 視覺方向

- 使用穩定、偏企業後台的深藍／藍綠色系，不採用工程工具常見的全黑頁面。
- 頁首使用活動名稱、時間與清楚狀態 badge。
- 使用四個摘要指標卡：要求內容、使用資料、產出數量、模型回應。
- Prompt 可使用深色閱讀區以區隔原文，但外層標題與說明維持一般管理者語言。
- 來源使用可掃讀的清單，每筆顯示名稱與摘要，不直接把 JSON 當作主要內容。
- 長內容保持可捲動，避免整頁高度失控；手機／窄螢幕改為單欄。

## 行為與錯誤處理

- 未登入或 session 過期時沿用現有登入導向。
- 搜尋與篩選不應遺失目前選取的 Campaign，除非使用者明確清除。
- 點擊活動索引後載入其 AI 活動；點擊活動紀錄後載入完整詳細內容。
- copy/download 失敗時顯示短暫、可理解的錯誤提示，不影響其他區段。
- 既有 query 上限、參數化查詢與 redaction 行為不變。

## 不在本次範圍

- 不新增自然語言搜尋。
- 不修改 PostgreSQL schema 或 payload capture 流程。
- 不將 Context Viewer 整合回原 frontend navigation。
- 不提供一般會員權限模型；維持目前獨立管理員登入。
- 不建立新的 LLM 結果編輯器或審核工作流。

## 驗收條件

- 非工程背景使用者能從 Campaign、日期／狀態、內容類型找到活動。
- 詳細頁首屏能清楚辨識活動名稱、狀態、時間與產出摘要。
- 使用者不閱讀 JSON 也能理解「要求 AI 做什麼」與「提供哪些資料」。
- 完整 prompt、來源與既有技術細節仍可查看、複製與下載。
- secret redaction、session protection、既有 API 與原 frontend 行為不退化。
- Context Viewer tests、production build 與相關 smoke tests 通過。
