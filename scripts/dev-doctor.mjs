import fs from "node:fs";
import net from "node:net";
import path from "node:path";
import { spawnSync } from "node:child_process";

const root = process.cwd();
const envPath = path.join(root, ".env.local");

function parsePort(value, fallback) {
  const num = Number(value ?? "");
  if (!Number.isFinite(num)) return fallback;
  const asInt = Math.trunc(num);
  if (asInt < 1 || asInt > 65535) return fallback;
  return asInt;
}

function loadEnvFile(filePath) {
  if (!fs.existsSync(filePath)) return {};
  const out = {};
  const raw = fs.readFileSync(filePath, "utf8");
  for (const line of raw.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const idx = trimmed.indexOf("=");
    if (idx <= 0) continue;
    out[trimmed.slice(0, idx).trim()] = trimmed.slice(idx + 1).trim();
  }
  return out;
}

function hasPythonModule(moduleName) {
  const cmd = process.platform === "win32" ? "python" : "python3";
  const res = spawnSync(cmd, ["-c", `import ${moduleName}`], { stdio: "ignore" });
  return res.status === 0;
}

function commandAvailable(command, args = ["--version"]) {
  const res =
    process.platform === "win32"
      ? spawnSync("cmd.exe", ["/c", command, ...args], { stdio: "ignore", shell: false })
      : spawnSync(command, args, { stdio: "ignore", shell: false });
  return res.status === 0;
}

function checkPort(port) {
  return new Promise((resolve) => {
    const socket = new net.Socket();
    socket.setTimeout(1000);
    socket.on("connect", () => {
      socket.destroy();
      resolve(true);
    });
    const done = () => resolve(false);
    socket.on("timeout", done);
    socket.on("error", done);
    socket.connect(port, "127.0.0.1");
  });
}

const env = { ...loadEnvFile(envPath), ...process.env };
const requirePostgres = String(env.CAMPAIGN_REQUIRE_POSTGRES ?? "true").trim().toLowerCase() !== "false";
const frontendPort = parsePort(env.DEV_FRONTEND_PORT, 3000);
const backendPort = parsePort(env.DEV_BACKEND_PORT, 8080);

const required = ["CHATBOT_INTERNAL_API_KEY"];
if (requirePostgres) {
  required.push("POSTGRES_DSN");
}
const missing = required.filter((key) => !(env[key] && String(env[key]).trim()));

const checks = [];
checks.push({ name: ".env.local exists", ok: fs.existsSync(envPath), detail: envPath });
checks.push({ name: "python module psycopg", ok: hasPythonModule("psycopg"), detail: "pip install psycopg[binary]" });
checks.push({ name: "python module uvicorn", ok: hasPythonModule("uvicorn"), detail: "pip install uvicorn" });
checks.push({ name: "python module fastapi", ok: hasPythonModule("fastapi"), detail: "pip install fastapi" });
checks.push({ name: "python module pydantic", ok: hasPythonModule("pydantic"), detail: "pip install pydantic" });
checks.push({ name: "python module multipart", ok: hasPythonModule("multipart"), detail: "pip install python-multipart" });
const npmCmd = process.platform === "win32" ? "npm.cmd" : "npm";
checks.push({ name: "npm available", ok: commandAvailable(npmCmd), detail: "npm --version" });
checks.push({ name: "required env vars", ok: missing.length === 0, detail: missing.length ? `Missing: ${missing.join(", ")}` : "ok" });
checks.push({ name: "CAMPAIGN_REQUIRE_POSTGRES", ok: true, detail: requirePostgres ? "true" : "false" });

const [frontendPortInUse, backendPortInUse] = await Promise.all([checkPort(frontendPort), checkPort(backendPort)]);
checks.push({
  name: `port ${frontendPort} available (DEV_FRONTEND_PORT)`,
  ok: !frontendPortInUse,
  detail: frontendPortInUse ? "in use" : "free",
});
checks.push({
  name: `port ${backendPort} available (DEV_BACKEND_PORT)`,
  ok: !backendPortInUse,
  detail: backendPortInUse ? "in use" : "free",
});

let hasFailure = false;
for (const item of checks) {
  const prefix = item.ok ? "[OK]" : "[FAIL]";
  if (!item.ok) hasFailure = true;
  console.log(`${prefix} ${item.name} - ${item.detail}`);
}

if (hasFailure) {
  process.exitCode = 1;
} else {
  console.log("[dev-doctor] PASS");
}
