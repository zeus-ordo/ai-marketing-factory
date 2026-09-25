import { readFileSync } from "node:fs";

const preview = readFileSync(new URL("../components/files/file-preview-modal.tsx", import.meta.url), "utf8");
const campaignsApi = readFileSync(new URL("../lib/api/campaigns.ts", import.meta.url), "utf8");
const campaigns = readFileSync(new URL("../app/campaigns/page.tsx", import.meta.url), "utf8");
const contentStudio = readFileSync(new URL("../app/content-studio/page.tsx", import.meta.url), "utf8");

for (const type of ["image", "video", "application/pdf"]) {
  if (!preview.includes(type)) throw new Error(`File preview must support ${type}.`);
}
if (!preview.includes("download")) throw new Error("File preview must provide a download fallback.");
if (!campaignsApi.includes("response.blob()")) throw new Error("Remote previews must load authenticated content as a blob.");
if (!campaignsApi.includes("Authorization")) throw new Error("Remote previews must send the access token.");
if (!campaigns.includes("<FilePreviewModal")) throw new Error("Campaign uploads must expose file preview.");
if (!contentStudio.includes("<FilePreviewModal")) throw new Error("Content library uploads must expose file preview.");
if (!contentStudio.includes("item.description")) throw new Error("Content library must expose text-only knowledge items for preview/download.");
if (!contentStudio.includes("new File([item.description")) throw new Error("Content library must preview text-only knowledge items.");
if (!contentStudio.includes("t(\"campaigns.knowledge.download\")")) throw new Error("Content library must expose a download action.");

console.log("File preview contract passed.");
