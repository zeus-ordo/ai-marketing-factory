import fs from "node:fs";
import path from "node:path";

function loadEnvFile(fileName) {
  const fullPath = path.resolve(process.cwd(), fileName);
  if (!fs.existsSync(fullPath)) return;
  for (const raw of fs.readFileSync(fullPath, "utf8").split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith("#")) continue;
    const idx = line.indexOf("=");
    if (idx <= 0) continue;
    const key = line.slice(0, idx).trim();
    const value = line.slice(idx + 1).trim();
    if (!(key in process.env)) process.env[key] = value;
  }
}

loadEnvFile(".env.local");

const BASE_URL = (process.env.E2E_BASE_URL ?? "http://localhost:3000").replace(/\/$/, "");
const INTERNAL_KEY = process.env.CHATBOT_INTERNAL_API_KEY ?? process.env.CAMPAIGN_INTERNAL_API_KEY ?? "";
const MAXLEN = Number.parseInt(process.env.OPS_TRIM_MAXLEN ?? "500", 10);
const TOPICS = ["task.copy", "task.image", "task.video", "task.ads", "task.dlq"];

if (!INTERNAL_KEY || INTERNAL_KEY.includes("change_me")) {
  console.error("[trim] FAIL CHATBOT_INTERNAL_API_KEY is missing or default");
  process.exit(1);
}

async function trimTopic(topic) {
  const res = await fetch(`${BASE_URL}/api/v1/system/operations/trim-topic`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "x-internal-api-key": INTERNAL_KEY },
    body: JSON.stringify({ topic, maxlen: MAXLEN, operator: "ops-script" }),
  });
  const payload = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(`${topic} (${res.status}): ${JSON.stringify(payload)}`);
  return payload;
}

try {
  console.log(`[trim] start maxlen=${MAXLEN}`);
  for (const topic of TOPICS) {
    const out = await trimTopic(topic);
    console.log(`[trim] ${out.topic ?? topic} trimmed=${out.trimmed ?? 0} maxlen=${out.maxlen ?? MAXLEN}`);
  }
  console.log("[trim] PASS");
} catch (error) {
  console.error("[trim] FAIL", error instanceof Error ? error.message : String(error));
  process.exit(1);
}
