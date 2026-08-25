import { readFile } from "node:fs/promises";

const source = await readFile(new URL("../app/campaigns/page.tsx", import.meta.url), "utf8");

if (!source.includes('const IMMEDIATE_UPLOAD_FOLDER = "即時上傳"')) {
  throw new Error("Campaign page must define the 即時上傳 folder constant");
}

if (!source.includes("uploadKnowledgeItem(knowledgeFile, knowledgeTitle || knowledgeFile.name, knowledgeDescription, IMMEDIATE_UPLOAD_FOLDER)")) {
  throw new Error("Campaign page upload flow must use IMMEDIATE_UPLOAD_FOLDER");
}

console.log("immediate upload folder test passed");
