import { readFileSync } from "node:fs";

const campaigns = readFileSync(new URL("../app/campaigns/page.tsx", import.meta.url), "utf8");

if (!campaigns.includes("editReferences")) throw new Error("Edit campaign must keep a campaign-specific reference list.");
if (!campaigns.includes("void loadEditReferences(campaignId)")) throw new Error("Edit campaign must load references for the edited campaign.");
if (!campaigns.includes("setEditReferences(await listCampaignReferences(campaignId))")) throw new Error("Edit campaign must load references for the edited campaign.");
if (!campaigns.includes("editReferences.map")) throw new Error("Edit campaign must render saved references.");
if (!campaigns.includes("reference.folder_id")) throw new Error("Edit campaign must show each reference folder.");
if (!campaigns.includes("bg-slate-950/80")) throw new Error("Edit campaign must use an opaque backdrop.");
if (!campaigns.includes(">Assets</h3>")) throw new Error("Generated outputs must be labeled Assets.");
if (campaigns.includes("bottom-4 left-4")) throw new Error("Temporary left floating reference panel must be removed.");
if (!campaigns.includes("right-8 top-24")) throw new Error("The saved Reference panel must remain visible on the right.");

console.log("Edit reference contract passed.");
