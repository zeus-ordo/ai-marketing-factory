import { readFile } from "node:fs/promises";

const page = await readFile(new URL("../app/campaigns/page.tsx", import.meta.url), "utf8");
const api = await readFile(new URL("../lib/api/campaigns.ts", import.meta.url), "utf8");
const translations = await readFile(new URL("../lib/i18n/translations.ts", import.meta.url), "utf8");

const assertions = [
  [api.includes("export type BatchUploadStatus = \"pending\" | \"uploading\" | \"success\" | \"failed\""), "typed per-file upload states are required"],
  [api.includes("preflightCampaignReferenceFiles"), "preflight validation helper is required"],
  [api.includes("REFERENCE_MAX_SIZE_BYTES") && api.includes("REFERENCE_ALLOWED_EXTENSIONS"), "preflight must enforce configured size and extensions"],
  [api.includes("REFERENCE_EXTENSION_MIME_TYPES"), "preflight must enforce MIME compatibility"],
  [api.includes("uploadCampaignReferences") && api.includes("concurrency"), "bounded batch upload helper is required"],
  [api.includes("for (let index = 0; index < files.length; index += 1)") || api.includes("while (nextIndex < pendingIndexes.length)"), "batch uploads must use a bounded worker queue"],
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
