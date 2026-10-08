import { readFileSync } from "node:fs";

const api = readFileSync(new URL("../lib/api/campaigns.ts", import.meta.url), "utf8");
const modal = readFileSync(new URL("../components/files/file-preview-modal.tsx", import.meta.url), "utf8");
const contentStudio = readFileSync(new URL("../app/content-studio/page.tsx", import.meta.url), "utf8");

if (!api.includes("export async function fetchCampaignContent")) throw new Error("Missing authorized campaign content helper.");
if (!api.includes("response.blob()")) throw new Error("Authorized campaign content helper must return a blob.");
if (!modal.includes("fetchCampaignContent")) throw new Error("File preview must use the campaign content helper.");
if (!modal.includes("URL.revokeObjectURL")) throw new Error("File preview must revoke object URLs.");
if (/href={item\.content_url}/.test(contentStudio)) throw new Error("Content studio must not link raw content_url values.");

console.log("Authorized content contract passed.");
