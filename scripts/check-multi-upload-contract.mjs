import { readFileSync } from "node:fs";

const files = {
  campaigns: readFileSync(new URL("../app/campaigns/page.tsx", import.meta.url), "utf8"),
  contentStudio: readFileSync(new URL("../app/content-studio/page.tsx", import.meta.url), "utf8"),
};

const inputs = [
  ["campaign content-library upload", files.campaigns, "key={knowledgeInputKey}", "multiple"],
  ["content-studio knowledge upload", files.contentStudio, "id={`knowledge-file-input-", "multiple"],
];

for (const [name, source] of Object.entries(files)) {
  if (!source.includes("MAX_BATCH_UPLOAD_FILES = 20")) {
    throw new Error(`${name} must enforce a 20-file batch limit.`);
  }
}

for (const [name, source, marker, required] of inputs) {
  const start = source.indexOf(marker);
  if (start < 0 || !source.slice(start, start + 350).includes(required)) {
    throw new Error(`${name} must support selecting multiple files.`);
  }
}

if (!files.campaigns.includes("uploadBatchItems(initialStates")) {
  throw new Error("Campaign content-library upload must use bounded batch upload handling.");
}

if (!files.contentStudio.includes("uploadBatchItems(initialStates")) {
  throw new Error("Content-studio upload must use bounded batch upload handling.");
}

if (!files.campaigns.includes("knowledgeCategory")) {
  throw new Error("Campaign content-library upload must expose a target folder selector.");
}

console.log("Multi-upload contract passed.");
