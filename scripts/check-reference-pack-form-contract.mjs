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
  "chooseFilesLabel",
  "selectedFilesLabel",
  "uploadFilesLabel",
  "noPackSelectedText",
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
const expectedAccept = 'accept="image/png,image/jpeg,image/webp,image/gif,text/plain,text/markdown,application/octet-stream,.txt,.md"';
if (!page.includes(expectedAccept)) failures.push("file input must accept image, text, and octet-stream reference formats");
if (!page.includes("onChange={(event) =>") || !page.includes("const referenceFiles = selected.map((file)") || !page.includes("isTextReferenceFile(file)")) failures.push("file input must classify selected files in its actual selection handler");
if (!page.includes('"application/octet-stream"')) failures.push("text classifier must accept application/octet-stream");
if (!page.includes("referencePacks.supportedFormatsLabel")) failures.push("page must show supported reference file formats");
if (!page.includes("referencePacks.textItemLabel")) failures.push("page must label text reference items");
if (!page.includes("referencePacks.chooseFilesLabel") || !page.includes("referencePacks.uploadFilesLabel") || !page.includes("referencePacks.noFilesLabel") || !page.includes("referencePacks.uploadSuccessLabel") || !page.includes("referencePacks.uploadFailedLabel") || !page.includes("referencePacks.deleteItemConfirmLabel") || !page.includes("referencePacks.deleteItemFailedLabel")) failures.push("page must use neutral file upload, status, and delete labels");
for (const key of ["supportedFormatsLabel", "textItemLabel", "chooseFilesLabel", "uploadFilesLabel", "noFilesLabel", "uploadSuccessLabel", "uploadFailedLabel", "deleteConfirmLabel", "deleteItemConfirmLabel", "deleteItemFailedLabel", "selectPackLabel"]) {
  const occurrences = translations.match(new RegExp(`\\b${key}:`, "g"))?.length ?? 0;
  if (occurrences !== 3) failures.push(`translation key ${key} must exist in all three locales (found ${occurrences})`);
  if (!page.includes(`referencePacks.${key}`)) failures.push(`page must use referencePacks.${key}`);
}
if (!page.includes("item.file_type") || !page.includes("item.file_size")) failures.push("page must render text item file metadata");
for (const oldCopy of [
  'accept="image/png,image/jpeg,image/webp,image/gif"',
  't("referencePacks.chooseImagesLabel")',
  't("referencePacks.uploadLabel")',
  't("referencePacks.noFiles")',
  't("referencePacks.noPackSelected")',
  't("referencePacks.uploaded")',
  't("referencePacks.uploadFailed")',
  't("referencePacks.deleteConfirm")',
  't("referencePacks.deleteItemConfirm")',
  't("referencePacks.deleteItemFailed")',
  't("referencePacks.selectPack")',
]) if (page.includes(oldCopy)) failures.push(`old image-only JSX/copy remains: ${oldCopy}`);
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
