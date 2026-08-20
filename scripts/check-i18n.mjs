import fs from "node:fs";
import path from "node:path";

const ROOT = process.cwd();
const TARGET_DIRS = ["app", "components"];
const EXTENSIONS = new Set([".tsx", ".ts"]);

const issues = [];

for (const relativeDir of TARGET_DIRS) {
  const absDir = path.join(ROOT, relativeDir);
  if (!fs.existsSync(absDir)) continue;
  walk(absDir);
}

if (issues.length > 0) {
  console.error("[check:i18n] Found potential hardcoded UI text:");
  for (const issue of issues) {
    console.error(`- ${issue.file}:${issue.line} ${issue.reason}`);
  }
  process.exit(1);
}

console.log("[check:i18n] OK - no hardcoded UI text detected by heuristic scan.");

function walk(dirPath) {
  const entries = fs.readdirSync(dirPath, { withFileTypes: true });
  for (const entry of entries) {
    const absPath = path.join(dirPath, entry.name);
    if (entry.isDirectory()) {
      walk(absPath);
      continue;
    }

    if (!entry.isFile()) continue;
    if (!EXTENSIONS.has(path.extname(entry.name))) continue;

    const content = fs.readFileSync(absPath, "utf8");
    scanFile(absPath, content);
  }
}

function scanFile(absPath, content) {
  const relPath = path.relative(ROOT, absPath).replaceAll("\\", "/");
  const lines = content.split(/\r?\n/);

  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i];
    const lineNumber = i + 1;
    const normalized = line.trim();

    if (shouldIgnoreLine(normalized)) continue;

    if (hasHardcodedJsxText(normalized)) {
      issues.push({ file: relPath, line: lineNumber, reason: "Hardcoded JSX text" });
    }

    if (hasHardcodedUiAttribute(normalized)) {
      issues.push({ file: relPath, line: lineNumber, reason: "Hardcoded placeholder/aria-label/title" });
    }
  }
}

function hasHardcodedJsxText(line) {
  const textNodeRegex = />\s*([^<{]*[A-Za-z\u4e00-\u9fff\u3040-\u30ff][^<{]*)\s*<\//;
  if (!textNodeRegex.test(line)) return false;
  if (line.includes("{t(")) return false;
  return true;
}

function hasHardcodedUiAttribute(line) {
  const attrRegex = /(placeholder|aria-label|title)\s*=\s*"[^"]*[A-Za-z\u4e00-\u9fff\u3040-\u30ff][^"]*"/;
  return attrRegex.test(line);
}

function shouldIgnoreLine(line) {
  if (!line) return true;
  if (line.startsWith("//")) return true;
  if (line.includes("http://") || line.includes("https://")) return true;
  if (line.includes("className=") || line.includes("import ")) return true;
  if (line.startsWith("<") && line.endsWith("/>")) return false;
  return false;
}
