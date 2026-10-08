import { readFileSync } from "node:fs";

const page = readFileSync(new URL("../app/content-studio/page.tsx", import.meta.url), "utf8");
const translations = readFileSync(new URL("../lib/i18n/translations.ts", import.meta.url), "utf8");

const requiredKeys = [
  "roleFilterLabel",
  "industryFilterLabel",
  "activeFilterLabel",
  "nameLabel",
  "roleLabel",
  "industryLabel",
  "selectionModeLabel",
  "maxImagesLabel",
  "priorityLabel",
  "activeLabel",
  "chooseImagesLabel",
  "selectedFilesLabel",
  "uploadLabel",
  "noPackSelected",
];

const requiredIds = [
  "reference-pack-role-filter",
  "reference-pack-industry-filter",
  "reference-pack-active-filter",
  "reference-pack-name",
  "reference-pack-role",
  "reference-pack-industry",
  "reference-pack-selection-mode",
  "reference-pack-max-images",
  "reference-pack-priority",
  "reference-pack-active",
  "reference-pack-file-input",
];

const failures = [];

for (const key of requiredKeys) {
  const occurrences = translations.match(new RegExp(`\\b${key}:`, "g"))?.length ?? 0;
  if (occurrences !== 3) failures.push(`translation key ${key} must exist in all three locales (found ${occurrences})`);
  if (!page.includes(`referencePacks.${key}`)) failures.push(`page must use referencePacks.${key}`);
}

for (const id of requiredIds) {
  if (!page.includes(`id="${id}"`)) failures.push(`page must include id=${id}`);
  if (id !== "reference-pack-file-input" && !page.includes(`htmlFor="${id}"`)) failures.push(`page must associate label with ${id}`);
}

if (!page.includes('htmlFor="reference-pack-file-input"')) failures.push("file input must have a matching label");
if (!page.includes('{!selectedPackId ? <p')) failures.push("page must guide users when no Pack is selected");
if (!page.includes('{selectedPackId ? <><div className="border-t border-slate-200 pt-3">')) failures.push("upload controls must remain conditional on selectedPackId");
if (!page.includes("await uploadReferencePackItems(uploadPackId, uploadStates, 3")) failures.push("existing upload API call must remain unchanged");
if (!page.includes("preflightCampaignReferenceFiles([file], uploadPolicy)")) failures.push("existing upload validation must remain unchanged");
if (!page.includes('<span className="truncate text-slate-900">{pack.name}</span>')) failures.push("Pack names on white cards must use text-slate-900");
if (!page.includes('<span className="text-xs text-slate-700">{pack.is_active ? t("referencePacks.active") : t("referencePacks.inactive")}</span>')) failures.push("Pack active state on white cards must use text-slate-700");
if (!page.includes('<span className="mt-1 block text-xs text-slate-700">{t(`referencePacks.roles.${pack.role}`)} · {pack.industry || t("referencePacks.global")} · {t("referencePacks.imageCount", { count: packCounts[pack.pack_id] ?? 0 })}</span>')) failures.push("Pack role, industry, and image count on white cards must use text-slate-700");

if (failures.length) {
  console.error("[check:reference-pack-form] Contract failures:");
  for (const failure of failures) console.error(`- ${failure}`);
  process.exit(1);
}

console.log("[check:reference-pack-form] OK");
