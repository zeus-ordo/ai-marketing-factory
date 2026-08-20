import fs from "node:fs";
import path from "node:path";
import { spawn, spawnSync } from "node:child_process";

const root = process.cwd();
const serviceDir = path.join(root, "services", "campaign_service");

function parsePort(value, fallback) {
  const num = Number(value ?? "");
  if (!Number.isFinite(num)) return fallback;
  const asInt = Math.trunc(num);
  if (asInt < 1 || asInt > 65535) return fallback;
  return asInt;
}

function loadEnv() {
  const envPath = path.join(root, ".env.local");
  const envFromFile = {};
  if (fs.existsSync(envPath)) {
    const raw = fs.readFileSync(envPath, "utf8");
    for (const line of raw.split(/\r?\n/)) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith("#")) continue;
      const idx = trimmed.indexOf("=");
      if (idx <= 0) continue;
      const k = trimmed.slice(0, idx).trim();
      const v = trimmed.slice(idx + 1).trim();
      envFromFile[k] = v;
    }
  }
  return { ...envFromFile, ...process.env };
}

function runDoctor() {
  const cmd = process.platform === "win32" ? "node" : "node";
  const res = spawnSync(cmd, ["scripts/dev-doctor.mjs"], { cwd: root, stdio: "inherit" });
  if (res.status !== 0) {
    throw new Error("dev-doctor failed. Fix issues before running dev-up.");
  }
}

function startProcess(name, command, args, cwd, env) {
  const logDir = path.join(root, ".sisyphus", "runtime-logs");
  fs.mkdirSync(logDir, { recursive: true });
  const outPath = path.join(logDir, `${name}.out.log`);
  const errPath = path.join(logDir, `${name}.err.log`);
  fs.writeFileSync(outPath, "");
  fs.writeFileSync(errPath, "");
  const out = fs.openSync(outPath, "w");
  const err = fs.openSync(errPath, "w");
  const child = spawn(command, args, {
    cwd,
    env,
    detached: true,
    stdio: ["ignore", out, err],
    shell: false,
  });
  child.unref();
  return child.pid;
}

async function waitForHttp(url, timeoutMs) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    try {
      const response = await fetch(url, { method: "GET", cache: "no-store" });
      if (response.ok) return true;
    } catch {
      // keep waiting
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  return false;
}

const env = loadEnv();
runDoctor();

const frontendPort = parsePort(env.DEV_FRONTEND_PORT, 3000);
const backendPort = parsePort(env.DEV_BACKEND_PORT, 8080);
env.PORT = String(frontendPort);

const normalizedApiBase = `http://localhost:${backendPort}`;
const normalizedMembershipApiBase = `http://localhost:${parsePort(env.DEV_MEMBERSHIP_PORT, 8095)}`;
if (!env.CAMPAIGN_API_BASE) {
  env.CAMPAIGN_API_BASE = normalizedApiBase;
}
if (!env.NEXT_PUBLIC_CAMPAIGN_API_BASE || env.NEXT_PUBLIC_CAMPAIGN_API_BASE === "/" || String(env.NEXT_PUBLIC_CAMPAIGN_API_BASE).includes(":8080")) {
  env.NEXT_PUBLIC_CAMPAIGN_API_BASE = normalizedApiBase;
}
if (!env.NEXT_PUBLIC_API_BASE || env.NEXT_PUBLIC_API_BASE === "/" || String(env.NEXT_PUBLIC_API_BASE).includes(":8080")) {
  env.NEXT_PUBLIC_API_BASE = normalizedApiBase;
}
if (!env.NEXT_PUBLIC_MEMBERSHIP_API_BASE || env.NEXT_PUBLIC_MEMBERSHIP_API_BASE === "/") {
  env.NEXT_PUBLIC_MEMBERSHIP_API_BASE = normalizedMembershipApiBase;
}

const npmCmd = process.platform === "win32" ? "npm.cmd" : "npm";
const pyCmd = process.platform === "win32" ? "python" : "python3";

const backendPid = startProcess(
  "campaign-api",
  pyCmd,
  ["-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", String(backendPort)],
  serviceDir,
  env,
);
const frontendPid = startProcess("frontend", npmCmd, ["run", "dev"], root, env);

const [backendReady, frontendReady] = await Promise.all([
  waitForHttp(`${normalizedApiBase}/health`, 20000),
  waitForHttp(`http://localhost:${frontendPort}`, 30000),
]);

if (!backendReady || !frontendReady) {
  throw new Error(
    `[dev-up] startup failed. backendReady=${backendReady}, frontendReady=${frontendReady}. Check .sisyphus/runtime-logs/*.log`,
  );
}

console.log(`[dev-up] PASS backend pid=${backendPid}, frontend pid=${frontendPid}`);
console.log("[dev-up] logs => .sisyphus/runtime-logs/*.log");
