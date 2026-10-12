import { readFileSync } from "node:fs";

const table = readFileSync(new URL("../components/review/review-queue-table.tsx", import.meta.url), "utf8");
const page = readFileSync(new URL("../app/review/page.tsx", import.meta.url), "utf8");

if (table.includes('t("review.table.generation")') || table.includes("<ProvenanceList")) {
  throw new Error("Review Center must not render the generation/source table column.");
}
if (page.includes("<ProvenanceList")) {
  throw new Error("Review Center must not render expanded provenance sources.");
}

console.log("Review compact contract passed.");
