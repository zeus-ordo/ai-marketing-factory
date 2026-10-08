import { readFileSync } from "node:fs";

const page = readFileSync(new URL("../app/campaigns/page.tsx", import.meta.url), "utf8");

if (!page.includes('value={campaignForm.industryCategory}')) {
  throw new Error("Campaign industry field was not found.");
}

const industryField = page.slice(page.indexOf('value={campaignForm.industryCategory}'), page.indexOf('value={campaignForm.industryCategory}') + 500);

if (!industryField.includes('t("campaigns.form.industryCategory")')) {
  throw new Error("Campaign industry field must use campaigns.form.industryCategory.");
}

if (industryField.includes('t("campaigns.knowledge.category")')) {
  throw new Error("Campaign industry field must not use the content-library category label.");
}

console.log("Campaign industry label contract passed.");
