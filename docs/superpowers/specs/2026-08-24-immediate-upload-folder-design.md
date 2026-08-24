# 「即時上傳」參考資料夾設計規格

## 1. 背景與問題

目前 Campaign 頁面的內容資料庫上傳流程將檔案的 `category` 預設設為
`General`。使用者完成上傳後，必須回到上方的 Reference 選擇區，卻無法
從分類上辨識這些剛上傳、主要供單次活動使用的參考檔案。

## 2. 目標

- 新增固定的「即時上傳」資料夾分類。
- 從 Campaign 頁面內的內容資料庫上傳檔案時，自動歸入「即時上傳」。
- 使用者可在同一個建立活動流程的 Reference 選擇區展開並勾選這些檔案。
- 檔案掛到活動後仍保留在「即時上傳」，可被其他活動重複使用。
- 不改變 Content Studio 正式資料庫上傳的既有分類行為。

## 3. 非目標

- 不自動搬移既有 `General` 檔案。
- 不在本次變更中建立每個活動專屬資料夾。
- 不在本次變更中刪除或自動封存已使用檔案。
- 不改變 Campaign Reference attach API 或資料庫 schema。

## 4. 使用者流程

1. 使用者進入建立 Campaign 頁面。
2. 在頁面下方的內容資料庫區域上傳新的 Reference 檔案。
3. 上傳完成後，檔案自動出現在「即時上傳」資料夾。
4. 使用者往上回到建立活動的 Reference 選擇區。
5. 展開「即時上傳」，勾選剛才的檔案。
6. 建立活動並確認。
7. 系統將選取的 Knowledge Item attach 到新活動。
8. 原始檔案仍留在「即時上傳」，之後可重複選用。

## 5. UI 與資料行為

### 5.1 固定資料夾

- 分類名稱：`即時上傳`
- 顯示位置：Campaign 頁面的內容資料庫與 Reference 選擇區
- 若目前沒有檔案，仍可顯示空資料夾，讓使用者知道上傳目的地。
- 不提供刪除或重新命名固定分類的操作。

### 5.2 Campaign 頁面上傳

Campaign 頁面現有的 `handleUploadKnowledgeItem` 呼叫
`uploadKnowledgeItem` 時，category 固定傳入 `即時上傳`，不再使用
`General` fallback。

Content Studio 頁面的上傳維持目前行為：

- 使用者指定資料夾時使用指定資料夾。
- 未指定時維持既有 `General` 行為。

### 5.3 重新載入與選取

- 上傳成功後重新載入 Knowledge Items。
- 現有 `getKnowledgeFolder`、資料夾分組及選取邏輯繼續使用。
- 「即時上傳」中的可 attach 檔案可被單檔或整個資料夾勾選。
- 建立活動成功後只清除目前頁面的選取狀態，不刪除 Knowledge Item。

## 6. API 與後端影響

本次不需新增 API 或資料庫欄位。既有 Knowledge Item upload API 已接受
`category` 欄位，前端只需傳入固定分類名稱。

若後端已有資料夾清單 API，固定分類應在前端選擇器中保證出現；不依賴
資料夾 API 是否已建立該名稱。

## 7. 相容性

- 既有 `General`、自訂資料夾及既有活動 Reference 不受影響。
- 舊檔案不自動搬移。
- Content Studio 原本的分類、移動與刪除功能維持不變。
- 多語系至少補上繁體中文文案；其他語系使用對應的固定翻譯字串。

## 8. 錯誤處理

- 上傳失敗時維持現有錯誤訊息與檔案選取狀態。
- 上傳成功但重新載入失敗時，顯示既有載入錯誤，不能清空使用者已輸入的
  其他欄位。
- 若 Knowledge Item 不可 attach，維持現有 disabled 顯示與原因提示。

## 9. 驗證計畫

1. 前端 typecheck/build 通過。
2. Campaign 頁面上傳檔案後，API 回應的 `metadata.category` 為 `即時上傳`。
3. Reference 選擇區能看到「即時上傳」資料夾及剛上傳檔案。
4. 選取檔案建立活動後，活動 Reference 清單包含該檔案。
5. 建立活動後重新載入 Knowledge Items，檔案仍存在於「即時上傳」。
6. Content Studio 上傳未指定資料夾時仍歸入 `General`。
7. 既有 `General` 檔案仍可被選取並 attach。
