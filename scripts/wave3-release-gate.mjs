import fs from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";

const root = process.cwd();
const serviceDir = path.join(root, "services", "campaign_service");

function loadDotEnvLocal() {
  const envFile = path.join(root, ".env.local");
  if (!fs.existsSync(envFile)) return;
  const raw = fs.readFileSync(envFile, "utf-8");
  for (const line of raw.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const idx = trimmed.indexOf("=");
    if (idx <= 0) continue;
    const key = trimmed.slice(0, idx).trim();
    const value = trimmed.slice(idx + 1).trim();
    if (!process.env[key]) {
      process.env[key] = value;
    }
  }
}

function runStep(label, command, args, cwd = root) {
  console.log(`\n[wave3-gate] ${label}`);
  const isWindows = process.platform === "win32";
  const result = isWindows
    ? spawnSync([command, ...args].join(" "), {
        cwd,
        stdio: "inherit",
        shell: true,
        env: process.env,
      })
    : spawnSync(command, args, {
        cwd,
        stdio: "inherit",
        shell: false,
        env: process.env,
      });

  if (result.error) {
    throw result.error;
  }
  if (result.status !== 0) {
    throw new Error(`${label} failed with exit code ${result.status ?? "unknown"}`);
  }
}

function main() {
  loadDotEnvLocal();

  const npmCommand = "npm";

  runStep("check:i18n", npmCommand, ["run", "check:i18n"]);
  runStep("lint", npmCommand, ["run", "lint"]);
  runStep("build", npmCommand, ["run", "build"]);
  runStep("compileall", "python", ["-m", "compileall", "app"], serviceDir);
  runStep("chatbot smoke", "node", ["scripts/chatbot-phase-d-smoke.mjs"]);

  console.log("\n[wave3-gate] PASS");
}

main();
