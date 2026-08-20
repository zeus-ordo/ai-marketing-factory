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

loadEnvFile(".env.test.local");

const BASE_URL = (process.env.E2E_BASE_URL ?? "http://localhost:3000").replace(/\/$/, "");
const AUTH_EMAIL = process.env.E2E_AUTH_EMAIL ?? "";
const AUTH_PASSWORD = process.env.E2E_AUTH_PASSWORD ?? "";

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function api(pathname, init = {}) {
  const response = await fetch(`${BASE_URL}${pathname}`, {
    ...init,
    headers: { ...(init.body ? { "Content-Type": "application/json" } : {}), ...(init.headers ?? {}) },
  });
  const contentType = response.headers.get("content-type") ?? "";
  const payload = contentType.includes("application/json") ? await response.json() : { detail: await response.text() };
  return { ok: response.ok, status: response.status, payload };
}

async function login() {
  const loginRes = await api("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({ email: AUTH_EMAIL, password: AUTH_PASSWORD }),
  });
  if (!loginRes.ok || !loginRes.payload?.access_token) {
    throw new Error(`login failed (${loginRes.status}): ${JSON.stringify(loginRes.payload)}`);
  }
  return { Authorization: `Bearer ${loginRes.payload.access_token}` };
}

async function check(name, pathname, init, validate = () => true) {
  const res = await api(pathname, init);
  assert(res.ok, `${name} failed (${res.status}): ${JSON.stringify(res.payload)}`);
  assert(validate(res.payload), `${name} returned unexpected payload: ${JSON.stringify(res.payload)}`);
  console.log(`✅ ${name}`);
  return res.payload;
}

try {
  console.log("[regression] start API regression checks");
  const authHeader = await login();
  await check("auth me", "/api/v1/auth/me", { headers: authHeader }, (p) => !!p.email || !!p.sub || !!p.user);
  const campaigns = await check("list campaigns", "/api/v1/campaigns", { headers: authHeader }, (p) => Array.isArray(p.items));
  const campaignId = campaigns.items?.find((item) => typeof item.campaign_id === "string")?.campaign_id;
  if (campaignId) await check("campaign tasks", `/api/v1/campaigns/${campaignId}/tasks`, { headers: authHeader }, (p) => Array.isArray(p.tasks));
  await check("review queue", "/api/v1/review/items?page=1&page_size=1&status=review_pending", { headers: authHeader });
  await check("queue health", "/api/v1/system/queue-health", { headers: authHeader });
  await check("operation audit logs", "/api/v1/system/operations/audit-logs?page=1&page_size=10", { headers: authHeader });
  await check("SLA backlog", "/api/v1/system/operations/sla-backlog?limit=10&overdue_only=true", { headers: authHeader });
  await check("redis stats", "/api/v1/system/operations/redis-stats", { headers: authHeader });
  await check("health check", "/api/v1/system/operations/health-check", { method: "POST", headers: authHeader, body: JSON.stringify({ operator: "regression" }) });
  await check("scan SLA", "/api/v1/system/operations/scan-sla", { method: "POST", headers: authHeader, body: JSON.stringify({ operator: "regression" }) });
  console.log("[regression] PASS");
} catch (error) {
  console.error("[regression] FAIL", error instanceof Error ? error.message : error);
  console.error("[regression] quick checks: 1) docker compose ps 2) auth login 3) API base / Caddy route 4) service logs");
  process.exit(1);
}
