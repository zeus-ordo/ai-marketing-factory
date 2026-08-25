import { readFile } from "node:fs/promises";

const source = await readFile(new URL("../app/campaigns/page.tsx", import.meta.url), "utf8");

if (!source.includes('const IMMEDIATE_UPLOAD_FOLDER = "即時上傳"')) {
  throw new Error("Campaign page must define the 即時上傳 folder constant");
}

if (!source.includes("uploadKnowledgeItem(knowledgeFile, knowledgeTitle || knowledgeFile.name, knowledgeDescription, IMMEDIATE_UPLOAD_FOLDER)")) {
  throw new Error("Campaign page upload flow must use IMMEDIATE_UPLOAD_FOLDER");
}

if (!source.includes("setFolders(Array.from(new Set([...data.items.map((f) => f.name), IMMEDIATE_UPLOAD_FOLDER])))")) {
  throw new Error("Campaign folder list must always include IMMEDIATE_UPLOAD_FOLDER");
}

if (!source.includes("const folderNames = new Set([")) {
  throw new Error("Campaign reference selector must include folders without items");
}

if (!source.includes('t("campaigns.knowledge.immediateUploadFolder")')) {
  throw new Error("Campaign page must translate the immediate upload folder label");
}

const translations = await readFile(new URL("../lib/i18n/translations.ts", import.meta.url), "utf8");
if (!translations.includes('immediateUploadFolder: "Immediate Upload"')) {
  throw new Error("English immediate upload folder translation is missing");
}
if (!translations.includes('immediateUploadFolder: "即時上傳"')) {
  throw new Error("Traditional Chinese immediate upload folder translation is missing");
}
if (!translations.includes('immediateUploadFolder: "即時アップロード"')) {
  throw new Error("Japanese immediate upload folder translation is missing");
}

console.log("immediate upload folder test passed");
