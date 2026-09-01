import { readFile } from "node:fs/promises";

const root = new URL("..", import.meta.url);
const campaignPage = await readFile(new URL("app/campaigns/page.tsx", root), "utf8");
const reviewPage = await readFile(new URL("app/review/page.tsx", root), "utf8");
const api = await readFile(new URL("lib/api/campaigns.ts", root), "utf8");
for (const [source, needle, message] of [
  [campaignPage, "generation_context_id", "Campaign page must display generation_context_id"],
  [campaignPage, "retryCampaignTask", "Campaign page must expose task retry"],
  [reviewPage, "internal_ratio", "Review page must display internal_ratio"],
  [reviewPage, "source_provenance", "Review page must display source provenance"],
  [api, "retryCampaignTask", "API client must call single-task retry"],
]) {
  if (!source.includes(needle)) throw new Error(message);
}
console.log("campaign flow contract passed");
