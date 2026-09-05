import { readFileSync } from "node:fs";

const api = readFileSync("lib/api/campaigns.ts", "utf8");
const contentStudio = readFileSync("app/content-studio/page.tsx", "utf8");
const campaigns = readFileSync("app/campaigns/page.tsx", "utf8");

for (const source of [api, contentStudio, campaigns]) {
  if (!source.includes("folder_id")) throw new Error("folder_id contract is missing");
}
if (!contentStudio.includes("read-only")) throw new Error("platform read-only UI contract is missing");
if (!api.includes("/api/v1/folders")) throw new Error("backend folder API contract is missing");

console.log("folder scope contract passed");
