import { readFileSync } from "node:fs";

const preview = readFileSync(new URL("../components/files/file-preview-modal.tsx", import.meta.url), "utf8");
const campaigns = readFileSync(new URL("../app/campaigns/page.tsx", import.meta.url), "utf8");
const contentStudio = readFileSync(new URL("../app/content-studio/page.tsx", import.meta.url), "utf8");

for (const type of ["image", "video", "application/pdf"]) {
  if (!preview.includes(type)) throw new Error(`File preview must support ${type}.`);
}
if (!preview.includes("download")) throw new Error("File preview must provide a download fallback.");
if (!campaigns.includes("<FilePreviewModal")) throw new Error("Campaign uploads must expose file preview.");
if (!contentStudio.includes("<FilePreviewModal")) throw new Error("Content library uploads must expose file preview.");

console.log("File preview contract passed.");
