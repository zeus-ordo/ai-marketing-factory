import fs from "node:fs";
import { execFileSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const CONFIG_PATTERN = /(^|\/)(\.env[^/]*|[^/]+\.(ya?ml|json|toml|ini|conf|bat|ps1|sh|bash|py|js|mjs|ts|tsx|jsx|md|txt|cmd|properties))$/i;
const LOCKFILE_PATTERN = /(?:package|npm|yarn|pnpm)-?lock\.(?:json|ya?ml)$/i;
const PLACEHOLDER_PATTERN = /^(?:<[^>]+>|change[_-]?me(?:[_-][^\s]+)?|replace[-_]?me|replace[-_]?with[-_]?.*|your[-_]?.*|example|test[-_]?.*|true|false|none|null)$/i;
const DSN_PATTERN = /(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?):\/\/[^/\s:@]+:([^@\s]+)@/i;
const TOKEN_PATTERN = /\b(?:sk|key|token|secret)[-_][A-Za-z0-9]{20,}\b/i;

function isVariableReference(value) {
  return /^\$[A-Za-z_][A-Za-z0-9_]*\b|^\{[A-Za-z_][A-Za-z0-9_]*\}$|^(?:process\.env|os\.environ|getenv\(|os\.getenv|env\(|Rand-|Read-Host|None|null|true|false|undefined)\b/i.test(value.trim());
}

function isPlaceholder(value) {
  const normalized = value.trim().replace(/^['"]|['"]$/g, "");
  if (PLACEHOLDER_PATTERN.test(normalized)) return true;
  const interpolation = normalized.match(/^\$\{[A-Za-z_][A-Za-z0-9_]*(?:(:?[-?])(.*))?\}$/);
  if (!interpolation) return false;
  if (!interpolation[1] || interpolation[1].endsWith("?")) return true;
  return !interpolation[2] || isPlaceholder(interpolation[2]);
}

function assignment(line) {
  return line.match(/^[\s"'\-]*(?:set\s+|export\s+)?(?:[\$]env:)?(?:(?:const|let|var)\s+)?["']?((?:[A-Za-z_][A-Za-z0-9_.-]*_)?(?:SECRET|TOKEN|API[_-]?KEY|PASSWORD|CREDENTIAL))["']?\s*([:=])\s*(.*)$/i);
}

function hasUnsafeInterpolation(value) {
  const matches = value.matchAll(/\$\{[A-Za-z_][A-Za-z0-9_]*(?:(:?[-?])(.*?))?\}/g);
  for (const match of matches) {
    if (match[1]?.endsWith("-") && match[2] && !isPlaceholder(match[2].trim())) return true;
  }
  return false;
}

export function findSecretIssues(entries, tracked = new Set(entries.map(([file]) => file))) {
  const issues = [];
  for (const [file, text] of entries) {
    if (/(?:^|[\\/])[^/\\]*(?:override|local-secrets)[^/\\]*\.(?:ya?ml|json)$/i.test(file) && tracked.has(file)) {
      issues.push({ file, key: "tracked-override" });
    }
    for (const raw of text.split(/\r?\n/)) {
      const line = raw.trim();
      if (!line || line.startsWith("#") || LOCKFILE_PATTERN.test(file)) continue;
      const dsn = line.match(DSN_PATTERN);
      if (dsn && !isPlaceholder(dsn[1]) && !isVariableReference(dsn[1]) && (!line.includes("${") || hasUnsafeInterpolation(line))) {
        issues.push({ file, key: "dsn-credential" });
        continue;
      }
      const match = assignment(line);
      if (match) {
        const key = match[1];
        const separator = match[2];
        const isStructuredConfig = /\.(?:ya?ml|json)$/i.test(file);
        if (separator === ":" && !isStructuredConfig) continue;
        const value = match[3].trim().replace(/[,;#].*$/, "").trim();
        if (/REQUIRE|ENABLED|PROVIDER|MODEL|URL|PORT|HEADER|COUNT|ACCESS_TOKEN_KEY|REFRESH_TOKEN_KEY/i.test(key)) continue;
        const literal = value.replace(/^['"]|['"]$/g, "");
        const isShellAssignment = /^(?:set\s+|export\s+|\$env:)/i.test(line);
        const isQuotedLiteral = /^["']/.test(value);
        const isLiteral = isStructuredConfig || isShellAssignment || isQuotedLiteral;
        if (hasUnsafeInterpolation(value) || (isLiteral && literal && !isVariableReference(literal) && !isPlaceholder(value))) {
          issues.push({ file, key });
          continue;
        }
      }
      if (TOKEN_PATTERN.test(line)) issues.push({ file, key: "credential-pattern" });
    }
  }
  return issues;
}

function trackedConfigEntries() {
  const tracked = execFileSync("git", ["ls-files", "-z"], { encoding: "utf8" }).split("\0").filter(Boolean);
  const files = tracked.filter((file) => !LOCKFILE_PATTERN.test(file) && CONFIG_PATTERN.test(file) && fs.existsSync(file));
  for (const candidate of [".env.local", ".env.test.local", "deploy/.env"]) {
    if (fs.existsSync(candidate) && !files.includes(candidate)) files.push(candidate);
  }
  return { files, entries: files.map((file) => [file, fs.readFileSync(file, "utf8")]) };
}

const { files, entries } = trackedConfigEntries();
if (path.resolve(process.argv[1] || "") === path.resolve(fileURLToPath(import.meta.url))) {
  const issues = findSecretIssues(entries, new Set(files));
  if (issues.length > 0) {
    console.error(`[secrets] FAIL weak or default secrets: ${issues.map(({ file, key }) => `${file}:${key}`).join(", ")}`);
    process.exit(1);
  }
  console.log("[secrets] PASS");
}
