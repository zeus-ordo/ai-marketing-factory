import { readFile } from "node:fs/promises";

const api = await readFile(new URL("../lib/api/campaigns.ts", import.meta.url), "utf8");
const page = await readFile(new URL("../app/content-studio/page.tsx", import.meta.url), "utf8");
const translations = await readFile(new URL("../lib/i18n/translations.ts", import.meta.url), "utf8");
const batchContract = await readFile(new URL("./test-batch-upload-contract.mjs", import.meta.url), "utf8");

const assertions = [
  [api.includes("KnowledgeItemAnalysisSummary"), "typed image analysis summary is required"],
  [api.includes("getKnowledgeItemAnalysis") && api.includes("/analysis`"), "knowledge analysis GET helper route is required"],
  [api.includes("retryKnowledgeItemAnalysis") && api.includes("/analysis/retry`"), "knowledge analysis retry helper route is required"],
  [api.includes("analysis?: KnowledgeItemAnalysisSummary | null") && api.includes("retryable"), "knowledge and pack records must expose safe analysis fields"],
  [page.includes("retryKnowledgeItemAnalysis"), "content studio must use the analysis retry helper"],
  [/items\.map\(\(item\) =>[\s\S]*?ImageAnalysisSummary[\s\S]*?item\.analysis/.test(page), "Pack item map must render the analysis summary"],
  [page.includes("retryPackItemAnalysis") && page.includes("onRetry={() => void retryPackItemAnalysis(item.item_id)}"), "Pack item retry action must call the shared retry helper"],
  [page.includes('data-testid="pack-analysis-items"') && page.includes("items.map((item) => <ImageAnalysisSummary"), "Pack analysis JSX render path is required"],
  [page.includes("isPlatformAdmin(user.permissions)") && page.includes("canManageReferencePacks"), "Pack analysis must remain platform-admin-only"],
  [/async function retryPackItemAnalysis[\s\S]*?await retryKnowledgeItemAnalysis\(itemId\)[\s\S]*?await loadItems\(selectedPackId\)/.test(page), "Pack retry must refresh the selected Pack items"],
  [page.includes("analysis_status") && page.includes("analysis_version") && page.includes("analyzed_at"), "content studio must render analysis status metadata"],
  [page.includes("analysisAttributeAllowlist") && page.includes("analysisSafeAttributeKeys"), "content studio must render allowlisted safe attributes"],
  [!page.includes("Object.entries(analysis.attributes)"), "analysis rendering must not enumerate runtime payload keys"],
  [page.includes("analysisReadyOnly"), "content studio must explain ready-only retrieval"],
  [page.includes("loadItems()") && page.includes("retryKnowledgeItemAnalysis"), "retry must refresh items once"],
  [translations.includes("analysisPending") && translations.includes("analysisProcessing") && translations.includes("analysisReady") && translations.includes("analysisFailed"), "analysis status labels are required"],
  [translations.includes("analysisRetry") && translations.includes("analysisAttributes") && translations.includes("analysisVersion") && translations.includes("analysisAnalyzedAt"), "analysis action and attribute labels are required"],
  [batchContract.includes("uploadReferencePackItems") && page.includes("uploadKnowledgeItem"), "existing upload contract must remain covered"],
  [page.includes("stored_path") && page.includes("vector") && page.includes("base64") && page.includes("provider"), "private analysis fields must be explicitly filtered"],
];

for (const [condition, message] of assertions) {
  if (!condition) throw new Error(message);
}

console.log(`image RAG upload contract test passed (${assertions.length} assertions)`);
