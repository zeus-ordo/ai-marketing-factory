# 新聞稿文案規則與 iNews RAG 入庫 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 將新聞稿規則統一為 1000–1400 字的可驗證契約，並把 `inews_word` 的 `.docx` 去重後匯入全域 iNews 參考資料 Pack 與向量資料庫。

**Architecture:** 文案規則文件與 worker／campaign-service 的 copy-length contract 使用同一組 1000–1400 字界線。iNews 匯入沿用既有文字 Reference Pack upload API 與 embedding pipeline；批次工具將 DOCX 在記憶體中轉成 TXT，再負責掃描、去重、上傳、輪詢狀態與輸出報告，不直接寫 PostgreSQL 或向量欄位。

**Tech Stack:** RTF、Python、FastAPI、PostgreSQL persistence、既有 knowledge-items/reference-packs API、pgvector／現有 embedding provider、pytest。

## Global Constraints

- 新聞稿字數固定為 **1000–1400 字**，至少三段。
- iNews 參考資料只用於寫作風格、結構與表達方式，不作為新活動事實來源。
- Pack 名稱固定為 `iNews 新聞稿參考資料`，scope 為 global。
- 所有 `.docx` 先以 SHA-256 去重，再在記憶體中轉成 `.txt`；不修改原始檔案，也不留下轉換檔。
- 只使用既有 upload／embedding pipeline，不直接寫入資料庫。
- 不把密碼、Token、API key、本機絕對路徑寫入日誌或 metadata。
- 不將文字參考資料送入圖片生成或圖片配額流程。

---

### Task 1: 建立可測試的新聞稿 copy-length contract

**Files:**
- Modify: `services/campaign_service/app/main.py`（新聞稿 task payload／copy contract 組裝處）
- Modify: `services/worker_copy/app/main.py`（動態 prompt、字數驗證與 repair 規則）
- Test: `services/campaign_service/test_copy_length_contract.py`
- Test: `services/worker_copy/test_copy_length.py`

**Interfaces:**
- `campaign-service` 傳給 worker 的 `body_min_length` 為 `1000`、`body_max_length` 為 `1400`。
- worker 的字數驗證仍使用 Unicode code point 計數，回傳既有 `invalid copy body length` 錯誤格式。
- 保留最多兩次 repair；repair 後仍不在範圍內即失敗。

- [ ] **Step 1: 寫 failing tests**

在既有 contract tests 增加：新聞稿 task 產生 1000／1400 邊界；999 與 1401 被拒絕；prompt 明確包含 `1000-1400`；repair 後仍超限會回傳既有錯誤。

```python
def test_news_release_contract_is_1000_to_1400():
    payload = build_copy_payload(task_type="copywriting", copy_type="news_release")
    assert payload["body_min_length"] == 1000
    assert payload["body_max_length"] == 1400
```

- [ ] **Step 2: 執行 failing tests**

Run: `pytest services/campaign_service/test_copy_length_contract.py services/worker_copy/test_copy_length.py -q`

Expected: 新增新聞稿界線測試 FAIL，現有社群／廣告測試保持原有結果。

- [ ] **Step 3: 實作最小變更**

只修改新聞稿類型的 contract mapping 與 prompt context；不要改動社群文章 300–500 字及廣告文案 80 字內的既有 contract。確保錯誤分類仍為 `invalid_copy_length`，不引入新的 retry 類型。

- [ ] **Step 4: 執行 focused tests**

Run: `pytest services/campaign_service/test_copy_length_contract.py services/worker_copy/test_copy_length.py -q`

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add services/campaign_service/app/main.py services/worker_copy/app/main.py services/campaign_service/test_copy_length_contract.py services/worker_copy/test_copy_length.py
git commit -m "feat: align news release copy length contract"
```

### Task 2: 優化 `文案規則.rtf`

**Files:**
- Modify: `C:\Users\User\Desktop\MF\文案規則.rtf`

**Interfaces:**
- 規則文件明確寫出新聞稿 1000–1400 字、至少三段、六要素、事實不可捏造、媒體聯絡資訊缺漏處理與驗收清單。
- 保留既有社群文章與廣告文案規則，僅改善語句、結構與可執行性。

- [ ] **Step 1: 將 RTF 內容重寫為分節規則**

使用 RTF Unicode escape 保持繁體中文可在 Windows／Office 開啟。新聞稿規則須包含：

```text
字數：1000–1400 字
格式：至少三段
首段：Who／What／When／Where／Why／How；輸入缺少的資訊不可捏造
中段：數據、背景、事件脈絡、產品或活動特色；引用必須來自輸入資料
結尾：發布／主辦單位背景、核心業務、官方連結（有提供才列）
文末：媒體聯絡人、職稱、電話、Email；未提供不得自行生成
禁則：社群 CTA、誇張標題、無來源推測、虛構事實
驗收：字數、段落、必要欄位、事實來源逐項檢查
```

- [ ] **Step 2: 以純文字解碼檢查 RTF**

Run a local read/decode check and verify the file contains `1000–1400`、`Who`、`What`、`When`、`Where`、`Why`、`How`、`不可捏造`、`媒體聯絡`。

- [ ] **Step 3: 保存並記錄變更**

`文案規則.rtf` 位於 repository 外的 MF 根目錄，因此不加入 `ai-marketing-factory` Git commit。完成後以解碼檢查結果與檔案修改時間記錄驗證，不複製或提交原始文件內容到 repository。

### Task 3: 建立可重跑的 iNews 批次匯入工具

**Files:**
- Create: `scripts/import_inews_references.py`（DOCX Open XML 轉 UTF-8 TXT、去重、上傳與輪詢）
- Create: `scripts/test_import_inews_references.py`
- Modify: `docs/admin-reference-packs-manual.txt`（加入批次匯入與 Ready 驗證說明）

**Interfaces:**
- CLI input：`--source-dir`、`--api-base-url`、`--pack-name`、`--report`、`--dry-run`。
- 預設 pack name：`iNews 新聞稿參考資料`。
- `POST /api/v1/reference-packs` 建立或重用同名 global pack。
- `POST /api/v1/reference-packs/{pack_id}/items/upload` 逐篇上傳記憶體中的 UTF-8 TXT multipart `title` 與 `file`；TXT 內嵌安全 provenance headers。
- `GET /api/v1/reference-packs/{pack_id}/items` 輪詢 item readiness；不直接寫 DB。
- 報告輸出檔名、SHA-256、item id、上傳狀態、Ready 狀態與安全錯誤訊息，不輸出本機完整路徑。

- [ ] **Step 1: 寫 failing tests**

覆蓋：遞迴只收 `.docx`、相同 SHA-256 只保留一次、title 從檔名移除副檔名、metadata 使用 `source=inews_word`／`reference_type=news_release_style`／`usage=style_and_structure_only`、dry-run 不發 request、HTTP 失敗只記錄檔名。

- [ ] **Step 2: 執行 failing tests**

Run: `pytest scripts/test_import_inews_references.py -q`

Expected: FAIL，因工具尚未存在。

- [ ] **Step 3: 實作 scanner、deduper、uploader 與 report writer**

使用 `pathlib.Path.rglob("*.docx")`；以 SHA-256 bytes 去重；使用 `urllib` 或專案既有 request helper 呼叫 API；每檔獨立捕捉 timeout／HTTP／validation error；重跑時先以 hash 與既有 item metadata 避免重複上傳。

- [ ] **Step 4: 執行 importer unit tests**

Run: `pytest scripts/test_import_inews_references.py -q`

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add scripts/import_inews_references.py scripts/test_import_inews_references.py docs/admin-reference-packs-manual.txt
git commit -m "feat: add idempotent iNews reference importer"
```

### Task 4: 執行 production 匯入與 RAG 驗證

**Files:**
- Create: `reports/inews-import-2026-11-04.json`（只含安全匯入結果）

**Interfaces:**
- 使用 Task 3 importer 對 `C:\Users\User\Desktop\MF\inews_word\inews_word` 執行。
- Production target：現有 campaign-service API，使用已授權 admin session／token；憑證只從環境變數或既有安全登入流程取得，不寫入 shell history、報告或 Git。

- [ ] **Step 1: 執行 dry-run**

Run:

```bash
python scripts/import_inews_references.py --source-dir "C:\Users\User\Desktop\MF\inews_word\inews_word" --pack-name "iNews 新聞稿參考資料" --dry-run --report reports/inews-import-2026-11-04-dry-run.json
```

Expected: 顯示 `.docx` 總數、SHA-256 去重數與預計上傳數；不建立 Pack、不上傳檔案。

- [ ] **Step 2: 執行正式匯入**

以安全 API session 執行相同命令但移除 `--dry-run`，輸出正式報告。若任一檔案失敗，保留失敗清單並只重試暫時性錯誤。

- [ ] **Step 3: 等待並檢查 Ready 狀態**

輪詢新 Pack items，直到每個成功上傳項目為 Ready、Failed 或 timeout；Failed 項目不宣稱完成，記入報告與後續 retry 清單。

- [ ] **Step 4: 執行 RAG smoke test**

以新聞稿開頭、事件背景、媒體聯絡資訊三種查詢確認結果可檢索；確認 Context Viewer 只顯示 pack／檔名／TXT provenance，不顯示本機路徑、Token 或內部 secrets。

- [ ] **Step 5: Commit safe report only**

```bash
git add reports/inews-import-2026-11-04.json
git commit -m "chore: record iNews reference import report"
```

### Task 5: 完整驗證與部署同步

**Files:**
- No new source files; inspect changes from Tasks 1–4.

- [ ] **Step 1: 執行 focused regression tests**

Run:

```bash
pytest services/campaign_service/test_copy_length_contract.py services/worker_copy/test_copy_length.py services/campaign_service/test_worker_result_state.py services/orchestrator/test_task_failure_isolation.py scripts/test_import_inews_references.py -q
```

Expected: PASS；若完整 campaign-service suite 出現既有 order-dependent JWT fixture failure，單獨重跑該測試並在結果中區分既有問題與本次變更。

- [ ] **Step 2: 執行 `git diff --check` 與敏感資料掃描**

確認沒有 credentials、Token、API key、本機絕對路徑或二進位文件被加入 Git。

- [ ] **Step 3: 檢查 production deployment revision**

確認 campaign-service／worker-copy 使用包含 1000–1400 contract 的 revision，且新 Pack item readiness 與報告一致。

- [ ] **Step 4: Commit verification notes if needed**

只有在需要保存安全驗證摘要時才提交；不得提交含憑證或敏感回應 body 的 log。
