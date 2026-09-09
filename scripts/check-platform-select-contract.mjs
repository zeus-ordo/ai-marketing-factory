import { readFileSync } from "node:fs";

const page = readFileSync(new URL("../app/campaigns/page.tsx", import.meta.url), "utf8");
const start = page.indexOf('value={campaignForm.platforms}');
const end = page.indexOf('</select>', start);
const select = page.slice(start, end);

const options = [["社群平台", "platformSocial"], ["廣告素材", "platformAds"], ["網站版位", "platformWeb"]];
for (const [value, key] of options) {
  if (!select.includes(`value="${value}"`)) throw new Error(`Missing platform option value: ${value}`);
  if (!select.includes(`t(\"campaigns.form.${key}\")`)) throw new Error(`Platform option must use its own label: ${value}`);
}

if (select.includes('t("campaigns.form.platforms")')) {
  throw new Error("Platform options must not all use the generic platforms label.");
}

console.log("Platform select contract passed.");
