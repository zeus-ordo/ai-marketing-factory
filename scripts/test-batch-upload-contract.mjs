import { readFile } from "node:fs/promises";
import ts from "typescript";

const page = await readFile(new URL("../app/campaigns/page.tsx", import.meta.url), "utf8");
const api = await readFile(new URL("../lib/api/campaigns.ts", import.meta.url), "utf8");
const helperSource = await readFile(new URL("../lib/api/batch-upload.ts", import.meta.url), "utf8");
const translations = await readFile(new URL("../lib/i18n/translations.ts", import.meta.url), "utf8");

const assertions = [
  [helperSource.includes("export type BatchUploadStatus = \"pending\" | \"uploading\" | \"success\" | \"failed\""), "typed per-file upload states are required"],
  [helperSource.includes("preflightCampaignReferenceFiles"), "preflight validation helper is required"],
  [helperSource.includes("REFERENCE_MAX_SIZE_BYTES") && helperSource.includes("REFERENCE_ALLOWED_EXTENSIONS"), "preflight must enforce configured size and extensions"],
  [helperSource.includes("REFERENCE_EXTENSION_MIME_TYPES"), "preflight must enforce MIME compatibility"],
  [api.includes("uploadCampaignReferences") && helperSource.includes("concurrency"), "bounded batch upload helper is required"],
  [helperSource.includes("while (nextIndex < pendingIndexes.length)"), "batch uploads must use a bounded worker queue"],
  [page.includes("fileStates.some((item) => item.status === \"failed\" || item.status === \"uploading\")"), "failed or incomplete uploads must block campaign start"],
  [page.includes("Promise.allSettled") && page.includes("result.status === \"rejected\""), "allSettled results must be inspected"],
  [page.includes('item.status === "failed"') && page.includes('item.status === "success"'), "page must retain per-file result state"],
  [page.includes("filter((item) => item.status === \"failed\")"), "retry must select failed files only"],
  [page.includes("reference_id") || page.includes("referenceId"), "successful reference IDs must be preserved"],
  [page.includes("Retry") || translations.includes("retryUpload"), "retry feedback/action is required"],
  [translations.includes("invalidFileType") && translations.includes("invalidFileSize") && translations.includes("uploading"), "upload validation and progress translations are required"],
  [translations.includes("partialUploadFailure") && translations.includes("campaignStartBlocked") && translations.includes("removeUpload"), "partial failure, blocked start, and remove translations are required"],
];

for (const [condition, message] of assertions) {
  if (!condition) throw new Error(message);
}

console.log(`batch upload contract test passed (${assertions.length} assertions)`);

const helperModule = ts.transpileModule(helperSource, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText;
const helper = await import(`data:text/javascript;base64,${Buffer.from(helperModule).toString("base64")}`);

const file = (name, type, size = 10) => ({ name, type, size });
const office = helper.preflightCampaignReferenceFiles([
  file("brief.docx", "application/octet-stream"),
  file("image.png", "text/plain"),
]);
if (office[0].status !== "pending" || office[1].errorCode !== "UNSUPPORTED_FILE_TYPE") {
  throw new Error("executable MIME preflight contract failed");
}

let active = 0;
let peak = 0;
const transitions = [];
const calls = [];
const states = await helper.uploadBatchItems(
  ["a.txt", "b.txt", "c.txt", "d.txt"].map((name) => ({ file: file(name, "text/plain"), status: "pending" })),
  async (current) => {
    active += 1;
    peak = Math.max(peak, active);
    await new Promise((resolve) => setTimeout(resolve, 2));
    calls.push(current.name);
    active -= 1;
    if (current.name === "b.txt") throw new Error("network detail must not escape");
    return { referenceId: `ref-${current.name}`, folderId: "folder-1" };
  },
  2,
  (current) => transitions.push(current.map((item) => item.status)),
);
if (peak > 2 || !transitions.some((value) => value.includes("uploading")) || states[1].status !== "failed" || states[0].referenceId !== "ref-a.txt" || states[0].folderId !== "folder-1") {
  throw new Error("executable bounded transition/failure propagation contract failed");
}

const retryCalls = [];
const retryStates = await helper.uploadBatchItems(
  [states[0], { ...states[1], status: "pending" }, states[2], states[3]],
  async (current) => {
    retryCalls.push(current.name);
    return { referenceId: `retry-${current.name}`, folderId: "folder-1" };
  },
  2,
);
if (retryCalls.join(",") !== "b.txt" || retryStates[0].referenceId !== "ref-a.txt" || retryStates[1].status !== "success") {
  throw new Error("executable retry-only-failed contract failed");
}

if (!page.includes("uploadBatchItems(knowledgeUploadStates") || !page.includes("removeKnowledgeUpload") || !page.includes('t("campaigns.form.uploadFailed")')) {
  throw new Error("knowledge retry/removal and localized stable error contract failed");
}

console.log("executable helper assertions passed (3 scenarios)");
