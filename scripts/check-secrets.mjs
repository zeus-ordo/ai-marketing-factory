import fs from "node:fs";
import { execFileSync } from "node:child_process";

const tracked = execFileSync("git", ["ls-files", "-z"], { encoding: "utf8" })
  .split("\0")
  .filter(Boolean);
const localCandidates = [".env.local", ".env.test.local", "deploy/.env"];
const configFiles = [...new Set([
  ...tracked.filter((file) => fs.existsSync(file) && !/(?:package|npm|yarn|pnpm)\-?lock\.json$/i.test(file) && /(^|\/)(\.env[^/]*|[^/]+\.(ya?ml|json|toml|ini|conf))$/i.test(file)),
  ...localCandidates.filter((file) => fs.existsSync(file)),
])];
const placeholder = /^(?:<[^>]+>|\$\{[^}]+\}|change[_-]?me(?:_[^\s]+)?|replace[-_]?me|replace[-_]?with[-_]?.*|your[-_]?.*|example|test[-_]?.*|password|true|false)$/i;
const secretKey = /(?:SECRET|TOKEN|KEY|PASSWORD|CREDENTIAL)/i;
const tokenPattern = /\b(?:sk|key|token|secret)[-_][A-Za-z0-9]{20,}\b/i;
const bad = [];

for (const file of configFiles) {
  const text = fs.readFileSync(file, "utf8");
  if (/\/[^/]*(?:override|local-secrets)[^/]*\.(?:ya?ml|json)$/i.test(`/${file}`) && tracked.includes(file)) {
    bad.push(`${file}:tracked-override`);
  }
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith("#")) continue;
    if (line.includes("${")) continue;
    const match = line.match(/^["']?([A-Za-z0-9_.-]*(?:SECRET|TOKEN|KEY|PASSWORD|CREDENTIAL)[A-Za-z0-9_.-]*)["']?\s*[:=]\s*["']?([^"'#,{\[]+)["']?/i);
    if (match && match[2].trim() && !placeholder.test(match[2].trim()) && !match[2].includes("${")) {
      bad.push(`${file}:${match[1]}`);
    } else if (tokenPattern.test(line)) {
      bad.push(`${file}:credential-pattern`);
    }
  }
}

if (bad.length > 0) {
  console.error(`[secrets] FAIL weak or default secrets: ${bad.join(", ")}`);
  process.exit(1);
}

console.log("[secrets] PASS");
