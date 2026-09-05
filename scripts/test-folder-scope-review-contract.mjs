import fs from "node:fs";

const contentStudio = fs.readFileSync("app/content-studio/page.tsx", "utf8");
const campaigns = fs.readFileSync("app/campaigns/page.tsx", "utf8");

if (contentStudio.includes("folders.find((folder) => folder.name ===") || campaigns.includes("folderRecords.find((folder) => folder.name ===")) {
  throw new Error("Folder selection must use folder_id, not name-only lookup");
}
if (!contentStudio.includes("folder.scope === \"platform\"")) {
  throw new Error("Content Studio must identify platform folders as read-only");
}
if (!contentStudio.includes("folder.folder_id") || !campaigns.includes("folder.folder_id")) {
  throw new Error("Folder UI must retain folder_id keys");
}
if (!campaigns.includes("folder.scope !== \"platform\"")) {
  throw new Error("Campaigns page must exclude platform folders from mutation targets");
}
if (!campaigns.includes("item.folder_id !== knowledgeCategoryFilter")) {
  throw new Error("Campaigns page filtering must use folder_id");
}
if (!campaigns.includes("getKnowledgeFolderKey(item, folderRecords)")) {
  throw new Error("Campaigns grouping must use folder_id keys");
}
if (!campaigns.includes("folder.company_id")) {
  throw new Error("Folder UI contract must retain company scope keys for duplicate names");
}
