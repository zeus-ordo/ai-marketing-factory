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
const PLATFORM_KEY = process.env.E2E_PLATFORM_KEY ?? "change_me_platform_admin_key";
const AUTH_EMAIL = process.env.E2E_AUTH_EMAIL ?? "";
const AUTH_PASSWORD = process.env.E2E_AUTH_PASSWORD ?? "";
const POLL_MAX = Math.max(80, Number.parseInt(process.env.E2E_POLL_MAX ?? "80", 10));
const POLL_INTERVAL_MS = Math.max(2000, Number.parseInt(process.env.E2E_POLL_INTERVAL_MS ?? "2000", 10));

let authHeader = null;

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function headers() {
  if (authHeader) return { "Content-Type": "application/json", ...authHeader };
  return { "Content-Type": "application/json", "x-platform-key": PLATFORM_KEY };
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

function summarizeTasks(tasks) {
  return tasks.map((task) => `${task.task_type}:${task.status}`).join(", ");
}

async function loginForJwt() {
  const resp = await api("/api/v1/auth/login", { method: "POST", body: JSON.stringify({ email: AUTH_EMAIL, password: AUTH_PASSWORD }) });
  if (!resp.ok || !resp.payload?.access_token) throw new Error(`jwt login failed (${resp.status}): ${JSON.stringify(resp.payload)}`);
  authHeader = { Authorization: `Bearer ${resp.payload.access_token}` };
}

async function preflight() {
  console.log("[e2e] preflight: check campaign api reachability");
  const list = await api("/api/v1/campaigns", { method: "GET", headers: headers() });
  if (!list.ok) {
    if ((list.status === 401 || list.status === 403) && !authHeader && AUTH_EMAIL && AUTH_PASSWORD) {
      console.log("[e2e] platform key rejected, fallback to JWT login");
      await loginForJwt();
      return preflight();
    }
    throw new Error(`preflight failed (${list.status}): ${JSON.stringify(list.payload)}`);
  }
}

async function createCampaign() {
  console.log("[e2e] create campaign");
  const body = {
    campaign_name: `E2E OneClick ${Date.now()}`,
    product_name: "OneClick Product",
    objective: "Increase conversion",
    target_audience: { age_range: "25-44", gender: "all", persona: "SMB owner" },
    platforms: ["LinkedIn"],
    budget: 12000,
    brand_tone: ["Professional"],
    deliverables: { copy_variants: 20, image_assets: 1, short_video_assets: 0, ads_strategy: 1 },
    mandatory_elements: [],
    forbidden_elements: [],
    deadline: "2026-12-31T00:00:00Z",
  };
  const created = await api("/api/v1/campaigns", { method: "POST", headers: headers(), body: JSON.stringify(body) });
  if ((created.status === 401 || created.status === 403) && !authHeader && AUTH_EMAIL && AUTH_PASSWORD) {
    console.log("[e2e] create unauthorized with platform key, fallback to JWT login");
    await loginForJwt();
    return createCampaign();
  }
  if (!created.ok) throw new Error(`create failed (${created.status}): ${JSON.stringify(created.payload)}`);
  assert(typeof created.payload.campaign_id === "string" && created.payload.campaign_id.startsWith("cmp_"), "invalid campaign_id");
  return created.payload.campaign_id;
}

async function runCampaign(campaignId) {
  console.log(`[e2e] run campaign ${campaignId}`);
  const run = await api(`/api/v1/campaigns/${campaignId}/run`, { method: "POST", headers: headers() });
  if (!run.ok) throw new Error(`run failed (${run.status}): ${JSON.stringify(run.payload)}`);
}

async function waitForTasks(campaignId) {
  console.log("[e2e] poll task completion");
  let lastTasks = [];
  for (let i = 1; i <= POLL_MAX; i += 1) {
    const tasksResp = await api(`/api/v1/campaigns/${campaignId}/tasks`, { method: "GET", headers: headers() });
    if (!tasksResp.ok) throw new Error(`tasks query failed (${tasksResp.status}): ${JSON.stringify(tasksResp.payload)}`);
    const tasks = tasksResp.payload.tasks ?? [];
    lastTasks = tasks;
    console.log(`[e2e] poll ${i}/${POLL_MAX}: ${summarizeTasks(tasks)}`);
    const done = tasks.length > 0 && tasks.every((t) => t.status === "passed" || t.status === "failed");
    if (done) {
      if (tasks.some((t) => t.status === "failed")) throw new Error(`task failure detected: ${summarizeTasks(tasks)}`);
      return tasks;
    }
    await sleep(POLL_INTERVAL_MS);
  }
  throw new Error(`task polling timeout: ${summarizeTasks(lastTasks)}`);
}

async function verifyBundle(campaignId) {
  console.log("[e2e] verify final bundle");
  const bundleResp = await api(`/api/v1/campaigns/${campaignId}/bundle`, { method: "GET", headers: headers() });
  if (!bundleResp.ok) throw new Error(`bundle query failed (${bundleResp.status}): ${JSON.stringify(bundleResp.payload)}`);
  const bundle = bundleResp.payload;
  const copyCount = Array.isArray(bundle.copy_assets) ? bundle.copy_assets.length : 0;
  const imageCount = Array.isArray(bundle.image_assets) ? bundle.image_assets.length : 0;
  const videoCount = Array.isArray(bundle.video_assets) ? bundle.video_assets.length : 0;
  const hasAds = !!bundle.ads_strategy && Object.keys(bundle.ads_strategy).length > 0;
  const invalidAssetUrls = [...(bundle.image_assets ?? []), ...(bundle.video_assets ?? [])]
    .map((asset) => asset?.url ?? "")
    .filter((url) => !url || url.startsWith("stub://") || url.startsWith("minimax://") || url.startsWith("minimax-quota://"));
  assert(copyCount > 0, "bundle has no copy assets");
  assert(imageCount > 0, "bundle has no image assets");
  assert(hasAds, "bundle has no ads strategy");
  assert(invalidAssetUrls.length === 0, `bundle contains invalid asset URLs: ${invalidAssetUrls.join(", ")}`);
  return { copyCount, imageCount, videoCount, hasAds };
}

async function verifyTrace(campaignId) {
  console.log("[e2e] verify trace endpoint access");
  const traceResp = await api(`/api/v1/campaigns/${campaignId}/trace/events?limit=20`, { method: "GET", headers: headers() });
  if (!traceResp.ok) throw new Error(`trace query failed (${traceResp.status}): ${JSON.stringify(traceResp.payload)}`);
  const total = Number(traceResp.payload.total ?? 0);
  assert(total >= 1, "trace should contain events");
  return total;
}

try {
  console.log("[e2e] start one-click verification");
  await preflight();
  const campaignId = await createCampaign();
  await runCampaign(campaignId);
  const tasks = await waitForTasks(campaignId);
  const bundle = await verifyBundle(campaignId);
  const traceTotal = await verifyTrace(campaignId);
  console.log("[e2e] PASS");
  console.log(JSON.stringify({ campaign_id: campaignId, tasks: summarizeTasks(tasks), bundle, trace_total: traceTotal }, null, 2));
} catch (error) {
  console.error("[e2e] FAIL", error instanceof Error ? error.message : error);
  process.exit(1);
}
