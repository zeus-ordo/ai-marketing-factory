# 新聞稿文案規則與 iNews 參考資料入庫設計

日期：2026-11-04
狀態：已獲使用者核准

## 目標

1. 優化 `C:\Users\User\Desktop\MF\文案規則.rtf`，使新聞稿規則可被人員與生成流程一致執行。
2. 將 `C:\Users\User\Desktop\MF\inews_word\inews_word` 內的新聞稿 `.docx` 作為新聞稿寫作風格與結構參考資料，送入 AI Marketing Factory 的文字 RAG／向量資料庫。

## 已確認的決策

- 所有 `inews_word` 內的 `.docx` 都納入處理。
- 新建全域 Reference Pack：`iNews 新聞稿參考資料`。
- 新聞稿的新字數限制採 **1000–1400 字**，取代原本只有「1000 字以上」的不完整規則。
- 參考新聞只用於寫作風格、結構與表達方式；不可被當成新活動的事實來源。
- 不將參考資料自動附加到既有 Campaign。

## 文案規則設計

`文案規則.rtf` 會保留社群文章與廣告文案規則，並重寫新聞稿規則，使其包含：

- 1000–1400 字，至少三段。
- 首段為完整新聞摘要，交代 Who、What、When、Where、Why、How；缺少的資訊不得捏造。
- 中段補充具體數據、背景、事件脈絡、產品或活動特色；可使用引用，但引用內容必須來自輸入資料。
- 結尾介紹發布／主辦單位、背景、歷史、核心業務與官方網站連結（若有提供）。
- 文末列出媒體聯絡人、職稱、電話與 Email；輸入未提供時不自行生成。
- 採客觀新聞稿語氣，避免社群 CTA、誇張標題、無來源推測與宣稱式內容。
- 生成前先檢查事實完整性，生成後檢查字數、段落、必要欄位與禁止事項。

系統端的 copy-length contract 也會同步使用 1000–1400 字，避免規則文件與 worker 驗證不一致。

## 參考資料入庫設計

### 資料處理

1. 遞迴掃描指定資料夾中的 `.docx`。
2. 以 SHA-256 去除完全相同的重複檔案；每篇保留獨立來源檔名與標題。
3. 使用既有 knowledge/reference upload API，不繞過系統 persistence 或 embedding pipeline。
4. 以批次併發上傳，但保留逐檔成功／失敗結果，支援失敗重試與重跑。

### Metadata

每筆資料標記：

- `source`: `inews_word`
- `reference_type`: `news_release_style`
- `usage`: `style_and_structure_only`
- 原始檔名與新聞標題

### Pack 與可用性

- Pack 名稱：`iNews 新聞稿參考資料`
- Scope：global
- 僅供文字 RAG／新聞稿上下文使用
- 不納入圖片配額、不送至圖片生成模型
- 只有解析與 embedding 狀態為 Ready 的資料可被檢索

## 錯誤處理

- 不支援、損壞或超過大小限制的檔案個別失敗，不影響其他檔案。
- API timeout、暫時性 provider error 可重試；驗證錯誤需記錄並停止該檔案重試。
- 不在日誌或 metadata 寫入密碼、Token、API key、本機絕對路徑或文件以外的敏感資訊。
- 批次完成後輸出總數、去重數、上傳成功數、Ready 數與失敗檔名清單。

## 驗證

### 規則

- 檢查 RTF 可正常開啟且包含 1000–1400 字新聞稿規則。
- 執行既有 campaign-service／worker-copy 的 focused tests。
- 驗證 worker 的輸入與 copy-length contract 都為 1000–1400 字。

### RAG

- 確認新 Pack 與所有成功上傳的 `.docx` 可列出。
- 確認所有成功資料最終為 Ready 且具有 embedding。
- 以新聞稿開頭、事件背景、媒體聯絡資訊等查詢做檢索 smoke test。
- 使用 Context Viewer 確認來源名稱正確，且沒有暴露本機路徑或內部資料。

## 不在本次範圍

- 不修改社群文章或廣告文案的字數規則，除非同步檢查發現與現有 contract 有直接衝突。
- 不清理或改寫原始 `inews_word` 文件。
- 不把 iNews 文章直接當作 Campaign 的事實資料或自動引用來源。
- 不建立新的 embedding provider；沿用現有 production pipeline。
