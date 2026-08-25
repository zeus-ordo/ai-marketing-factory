# 「即時上傳」參考資料夾 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make files uploaded from the Campaign page's embedded Content Library automatically appear in a persistent `即時上傳` folder that can be selected as campaign references and reused later.

**Architecture:** Keep the existing Knowledge Item API and metadata category model. Change only the Campaign page's upload category to a fixed label, ensure that label is always present in the Campaign page folder selectors, and leave Content Studio's existing `General`/custom-folder behavior unchanged.

**Tech Stack:** Next.js 16, React 19, TypeScript, existing Knowledge Item and Campaign Reference APIs, existing i18n translations.

## Global Constraints

- Do not automatically move existing `General` files.
- Do not create per-campaign folders.
- Do not delete or archive files after they are attached to a campaign.
- Do not change the Campaign Reference API or database schema.
- Existing `General`, custom folders, and existing campaign references must remain compatible.
- The fixed `即時上傳` category cannot be deleted or renamed through this feature.

---

### Task 1: Add the fixed folder constant and regression test

**Files:**
- Create: `scripts/test-immediate-upload-folder.mjs`
- Modify: `app/campaigns/page.tsx:1-20`

**Interfaces:**
- Produces a single Campaign-page constant, `IMMEDIATE_UPLOAD_FOLDER`, with value `"即時上傳"`.
- The test script reads the Campaign page source and verifies the fixed category and upload usage exist.

- [ ] **Step 1: Write the failing regression test**

Create `scripts/test-immediate-upload-folder.mjs`:

```js
import { readFile } from "node:fs/promises";

const source = await readFile(new URL("../app/campaigns/page.tsx", import.meta.url), "utf8");

if (!source.includes('const IMMEDIATE_UPLOAD_FOLDER = "即時上傳"')) {
  throw new Error("Campaign page must define the 即時上傳 folder constant");
}

if (!source.includes("uploadKnowledgeItem(knowledgeFile")) {
  throw new Error("Campaign page upload handler is missing");
}

if (!source.includes("IMMEDIATE_UPLOAD_FOLDER")) {
  throw new Error("Campaign page upload flow must use IMMEDIATE_UPLOAD_FOLDER");
}

console.log("immediate upload folder test passed");
```

- [ ] **Step 2: Run the test and verify it fails for the missing constant**

Run:

```bash
node scripts/test-immediate-upload-folder.mjs
```

Expected: FAIL with `Campaign page must define the 即時上傳 folder constant`.

- [ ] **Step 3: Add the minimal constant**

Near the Campaign page's local type/constants, add:

```ts
const IMMEDIATE_UPLOAD_FOLDER = "即時上傳";
```

- [ ] **Step 4: Run the test and verify it passes**

Run:

```bash
node scripts/test-immediate-upload-folder.mjs
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/test-immediate-upload-folder.mjs app/campaigns/page.tsx
git commit -m "Add immediate upload folder constant"
```

### Task 2: Route Campaign-page uploads into 「即時上傳」

**Files:**
- Modify: `app/campaigns/page.tsx:915-937`

**Interfaces:**
- Consumes: `IMMEDIATE_UPLOAD_FOLDER` from Task 1 and existing `uploadKnowledgeItem`.
- Produces: Knowledge Items uploaded from Campaign page with `category === "即時上傳"`.

- [ ] **Step 1: Update the upload handler**

Change the existing call in `handleUploadKnowledgeItem` from:

```ts
await uploadKnowledgeItem(knowledgeFile, knowledgeTitle || knowledgeFile.name, knowledgeDescription, knowledgeCategory || "General");
```

to:

```ts
await uploadKnowledgeItem(
  knowledgeFile,
  knowledgeTitle || knowledgeFile.name,
  knowledgeDescription,
  IMMEDIATE_UPLOAD_FOLDER,
);
```

Do not change `app/content-studio/page.tsx`; its upload category behavior remains unchanged.

- [ ] **Step 2: Run the regression test**

Run:

```bash
node scripts/test-immediate-upload-folder.mjs
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add app/campaigns/page.tsx
git commit -m "Route campaign uploads to immediate upload folder"
```

### Task 3: Always expose 「即時上傳」 in Campaign folder selectors

**Files:**
- Modify: `app/campaigns/page.tsx:341-347, 391-415, 1167-1237`
- Modify: `lib/i18n/translations.ts` in the Campaign knowledge/reference labels for English, Traditional Chinese, and Japanese.

**Interfaces:**
- Consumes: `IMMEDIATE_UPLOAD_FOLDER`, existing `folders`, `knowledgeItems`, and `groupedKnowledgeItems`.
- Produces: A visible, selectable empty or populated `即時上傳` folder in the Campaign page's knowledge upload and Reference selection UI.

- [ ] **Step 1: Extend the Campaign folder list with the fixed folder**

When loading folder names for the Campaign page, merge the API folders with the fixed folder and de-duplicate it:

```ts
setFolders((data.items.map((folder) => folder.name).concat(IMMEDIATE_UPLOAD_FOLDER)));
```

Use a `Set` before storing if needed so the folder appears only once.

- [ ] **Step 2: Ensure the grouped Reference selector renders an empty fixed folder**

Build the displayed folder names from both item categories and `folders`, always including `IMMEDIATE_UPLOAD_FOLDER`. For folders with no items, render an empty folder row with its checkbox disabled and no delete action. For folders with items, preserve the existing folder-level and file-level selection behavior.

The resulting grouping must include the equivalent of:

```ts
const folderNames = new Set([
  ...folders,
  ...knowledgeCategories,
  IMMEDIATE_UPLOAD_FOLDER,
]);
```

Render the stored category through a small display helper so the persisted
value remains `即時上傳` while the visible label uses the active locale:

```ts
function getKnowledgeFolderLabel(folderName: string): string {
  return folderName === IMMEDIATE_UPLOAD_FOLDER
    ? t("campaigns.knowledge.immediateUploadFolder")
    : folderName;
}
```

Use the helper only for visible labels; use the raw folder name for filtering,
selection state, and API payloads.

- [ ] **Step 3: Protect the fixed folder from folder-management actions**

Where the Campaign page exposes folder deletion or rename controls, hide or disable those controls when the folder name is `IMMEDIATE_UPLOAD_FOLDER`. Do not change Content Studio's custom folder management behavior.

- [ ] **Step 4: Add translated UI labels**

Add translations for the fixed folder label/help text in the existing Campaign knowledge/reference translation sections. Use:

```text
English: Immediate Upload
繁體中文: 即時上傳
日本語: 即時アップロード
```

The translation key is `campaigns.knowledge.immediateUploadFolder`.

Keep the stored category value exactly `即時上傳` for compatibility with current metadata filtering.

- [ ] **Step 5: Run frontend checks**

Run:

```bash
node scripts/test-immediate-upload-folder.mjs
npm run build
```

Expected: regression test PASS and Next.js build PASS.

- [ ] **Step 6: Commit**

```bash
git add app/campaigns/page.tsx lib/i18n/translations.ts
git commit -m "Show immediate upload folder in campaign references"
```

### Task 4: Verify the complete user flow

**Files:**
- Modify: none
- Test: deployed GCP frontend and API

**Interfaces:**
- Consumes: the Campaign page upload and selection behavior from Tasks 1–3.
- Produces: evidence that uploaded files remain reusable after campaign attachment.

- [ ] **Step 1: Deploy the frontend image**

After pushing the implementation commits:

```bash
gcloud compute ssh ai-marketing-factory --zone=asia-east1-a --command="cd /opt/ai-marketing-factory && git pull origin master && cd deploy && docker compose -f docker-compose.gcp.yml up -d --build frontend"
```

- [ ] **Step 2: Verify upload metadata**

Log in as `admin@techcorp.co`, upload a test reference from the Campaign page, and confirm the Knowledge Item response contains:

```json
{"metadata":{"category":"即時上傳"}}
```

- [ ] **Step 3: Verify selection and attachment**

Return to the Reference selector, expand `即時上傳`, select the uploaded file, create a Campaign, and confirm the new Campaign's References list contains the file.

- [ ] **Step 4: Verify reuse**

Reload the Campaign page and confirm the same file remains under `即時上傳`. Create a second test Campaign and attach the same file.

- [ ] **Step 5: Verify backward compatibility**

Confirm an existing `General` item remains visible and selectable, and confirm a file uploaded from Content Studio without a selected custom folder continues to use `General`.

- [ ] **Step 6: Record deployment verification**

Run:

```bash
docker ps --format "table {{.Names}}\t{{.Status}}"
```

Expected: frontend and all existing services remain `Up`.
