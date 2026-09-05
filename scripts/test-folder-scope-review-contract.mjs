import fs from "node:fs";

const contentStudio = fs.readFileSync("app/content-studio/page.tsx", "utf8");
const campaigns = fs.readFileSync("app/campaigns/page.tsx", "utf8");

if (contentStudio.includes("folders.find((folder) => folder.name ===") || campaigns.includes("folderRecords.find((folder) => folder.name ===")) {
  throw new Error("Folder selection must use folder_id, not name-only lookup");
}
if (!contentStudio.includes("folder.scope === \"platform\"")) {
  throw new Error("Content Studio must identify platform folders as read-only");
}
