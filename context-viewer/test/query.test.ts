import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { buildCampaignQuery, buildContextDetailQuery, buildContextListQuery, redactSecrets } from "../lib/query.ts";
import { isValidSession, signSession } from "../lib/session.ts";
import { GET as campaigns } from "../app/api/campaigns/route.ts";
import { GET as contexts } from "../app/api/contexts/route.ts";
import { GET as detail } from "../app/api/contexts/[generationContextId]/route.ts";
import { POST as login } from "../app/api/login/route.ts";

test("buildContextListQuery parameterizes filters and caps the page", () => {
  const query = buildContextListQuery({
    campaignId: "campaign' OR 1=1 --",
    generationContextId: "context-1",
    runId: "run-1",
    limit: 9999,
    offset: 4,
  });

  assert.match(query.text, /WHERE/);
  assert.match(query.text, /LIMIT \$\d+ OFFSET \$\d+/);
  assert.ok(!query.text.includes("campaign' OR 1=1"));
  assert.deepEqual(query.values, ["campaign' OR 1=1 --", "context-1", "run-1", 100, 4]);
});

test("buildContextListQuery parameterizes administrator activity filters", () => {
  const query = buildContextListQuery({
    campaignId: "spring-launch",
    activityType: "copywriting",
    status: "completed",
    from: "2026-09-01",
    to: "2026-09-30",
  });

  assert.match(query.text, /created_at/);
  assert.match(query.text, /task_type|activity_type/);
  assert.ok(!query.text.includes("spring-launch"));
  assert.ok(query.values.includes("copywriting"));
  assert.ok(query.values.includes("completed"));
  assert.ok(query.values.includes("2026-09-01"));
  assert.ok(query.values.includes("2026-09-30"));
});

test("campaign query exposes a brief campaign name and parameterizes name or id search", () => {
  const query = buildCampaignQuery("Spring' OR 1=1 --");

  assert.match(query.text, /brief_json\s*->>\s*'campaign_name'/);
  assert.match(query.text, /campaign_id\s+ILIKE\s+\$1/);
  assert.match(query.text, /campaign_name|brief_json/);
  assert.ok(!query.text.includes("Spring' OR 1=1"));
  assert.deepEqual(query.values, ["%Spring' OR 1=1 --%"]);
});

test("context activity query exposes the persisted campaign name with an id fallback", () => {
  const query = buildContextListQuery();

  assert.match(query.text, /COALESCE\(NULLIF\(c\.brief_json\s*->>\s*'campaign_name',\s*''\),\s*c\.campaign_id\)\s+AS\s+campaign_name/);
  assert.match(query.text, /brief_json\s*->>\s*'campaign_name'/);
});

test("buildContextListQuery selects activity without reducing payload aggregation", () => {
  const query = buildContextListQuery({ activityType: "copywriting" });

  assert.match(query.text, /EXISTS\s*\(/);
  assert.match(query.text, /lp\.task_type/);
  assert.match(query.text, /COUNT\(DISTINCT lp\.payload_id\)/);
  assert.match(query.text, /LEFT JOIN llm_generation_payloads lp[\s\S]*GROUP BY/);
  assert.match(query.text, /generation_context_id = gc\.generation_context_id/);
});

test("buildContextListQuery includes task-only activity matches", () => {
  const query = buildContextListQuery({ activityType: "copywriting" });

  assert.match(query.text, /ct\.task_type\s*=\s*\$\d+\s+OR\s+EXISTS/);
  assert.match(query.text, /lp_filter\.task_type\s*=\s*\$\d+/);
});

test("buildContextListQuery keeps offset finite and capped", () => {
  const nonFiniteQuery = buildContextListQuery({ offset: Number.POSITIVE_INFINITY });
  const cappedQuery = buildContextListQuery({ offset: 999_999 });

  assert.equal(nonFiniteQuery.values.at(-1), 0);
  assert.equal(cappedQuery.values.at(-1), 100_000);
  assert.ok(Number.isFinite(nonFiniteQuery.values.at(-1) as number));
  assert.ok(Number.isFinite(cappedQuery.values.at(-1) as number));
});

test("redactSecrets removes case and format variants but preserves ordinary prompt text", () => {
  const result = redactSecrets({
    prompt: "Write a launch email for our token rewards program.",
    api_key: "do-not-return",
    apiKey: "do-not-return",
    access_token: "do-not-return",
    client_secret: "do-not-return",
    credential_id: "do-not-return",
    credentialId: "do-not-return",
    api_key_secret: "do-not-return",
    refresh_token: "do-not-return",
    accessToken: "do-not-return",
    nested: { authorization: "Bearer do-not-return", audience: "customers" },
    items: [{ password: "hidden" }, { text: "ordinary context" }],
  });

  assert.equal(result.prompt, "Write a launch email for our token rewards program.");
  assert.equal(result.api_key, "[REDACTED]");
  assert.equal(result.apiKey, "[REDACTED]");
  assert.equal(result.access_token, "[REDACTED]");
  assert.equal(result.client_secret, "[REDACTED]");
  assert.equal(result.credential_id, "[REDACTED]");
  assert.equal(result.credentialId, "[REDACTED]");
  assert.equal(result.api_key_secret, "[REDACTED]");
  assert.equal(result.refresh_token, "[REDACTED]");
  assert.equal(result.accessToken, "[REDACTED]");
  assert.equal(result.nested.authorization, "[REDACTED]");
  assert.equal(result.nested.audience, "customers");
  assert.equal(result.items[0].password, "[REDACTED]");
  assert.equal(result.items[1].text, "ordinary context");
});

test("redactSecrets removes secret-bearing strings in payloads and URLs", () => {
  const result = redactSecrets({
    prompt: "Discuss token rewards with customers.",
    error: "Authorization: Bearer super-secret-token",
    callback_url: "https://example.test/callback?api_key=url-secret&campaign=summer",
    database_url: "postgres://user:db-secret@example.test/marketing",
    ordinary_url: "https://example.test/products?campaign=summer",
  });

  assert.equal(result.prompt, "Discuss token rewards with customers.");
  assert.equal(result.error, "Authorization: Bearer [REDACTED]");
  assert.equal(result.callback_url, "https://example.test/callback?api_key=[REDACTED]&campaign=summer");
  assert.equal(result.database_url, "postgres://user:[REDACTED]@example.test/marketing");
  assert.equal(result.ordinary_url, "https://example.test/products?campaign=summer");
});

test("redactSecrets preserves token count metadata", () => {
  const result = redactSecrets({
    internal_token_count: 12,
    external_token_count: 34,
    token: "secret-token",
  });

  assert.equal(result.internal_token_count, 12);
  assert.equal(result.external_token_count, 34);
  assert.equal(result.token, "[REDACTED]");
});

test("invalid or absent session cookies are rejected", () => {
  assert.equal(isValidSession(undefined, "test-secret"), false);
  assert.equal(isValidSession("not-a-session", "test-secret"), false);
  assert.equal(isValidSession(`${signSession("admin", "test-secret")}tampered`, "test-secret"), false);
  assert.equal(isValidSession(signSession("admin", "test-secret", 1_000, 60), "test-secret", 62_000), false);
  assert.equal(isValidSession(`${signSession("admin", "test-secret", 1_000, 60)}.extra`, "test-secret", 1_001), false);
});

test("protected routes reject requests without a valid session", async () => {
  const response = await campaigns(new Request("http://localhost/api/campaigns"));
  assert.equal(response.status, 401);
  const listResponse = await contexts(new Request("http://localhost/api/contexts"));
  assert.equal(listResponse.status, 401);
  const detailResponse = await detail(new Request("http://localhost/api/contexts/context-1"), { params: Promise.resolve({ generationContextId: "context-1" }) });
  assert.equal(detailResponse.status, 401);
});

test("detail query retains the persisted worker context JSON", () => {
  const query = buildContextDetailQuery("context-1");
  assert.match(query.text, /jsonb_build_object/);
  assert.match(query.text, /jsonb_agg\(jsonb_build_object/);
  assert.match(query.text, /context_json/);
});

test("detail query returns generation context metadata and the UI renders a metadata panel", async () => {
  const query = buildContextDetailQuery("context-1");
  for (const field of ["campaign_id", "run_id", "generation_context_id", "internal_token_count", "external_token_count", "internal_ratio", "external_ratio", "external_source_urls_json", "external_search_status", "external_search_error", "task_id", "selected_reference_ids_json", "matched_folder_names_json"]) {
    assert.match(query.text, new RegExp(`gc\\.${field}`));
  }
  const page = await readFile(new URL("../app/page.tsx", import.meta.url), "utf8");
  assert.match(page, /Generation context metadata/);
  assert.match(page, /external_source_urls_json/);
});

test("administrator activity workbench exposes management labels and filter controls", async () => {
  const page = await readFile(new URL("../app/page.tsx", import.meta.url), "utf8");
  for (const label of ["AI activity", "Campaign", "Date", "Content type", "Status", "Clear filters", "No AI activity found", "Next step"]) {
    assert.match(page, new RegExp(label));
  }
});

test("administrator workbench wires campaign search and surfaces campaign load errors", async () => {
  const page = await readFile(new URL("../app/page.tsx", import.meta.url), "utf8");
  assert.match(page, /value=\{campaignSearch\}/);
  assert.match(page, /setCampaignSearch\(/);
  assert.match(page, /loadCampaigns\(\)/);
  assert.match(page, /Could not load campaigns|Unable to load campaigns|campaignError/);
  assert.match(page, /campaign_name/);
});

test("activity record detail uses readable administrator sections and actions", async () => {
  const page = await readFile(new URL("../app/page.tsx", import.meta.url), "utf8");
  for (const label of [
    "What we asked the AI to do",
    "Information given to the AI",
    "What the AI returned",
    "Copy instruction",
    "View all information",
    "Technical details",
  ]) {
    assert.match(page, new RegExp(label));
  }
  assert.match(page, /internal_token_count/);
  assert.match(page, /external_token_count/);
  assert.match(page, /Back to activity list/);
});

test("activity record detail preserves filters and reports action failures", async () => {
  const page = await readFile(new URL("../app/page.tsx", import.meta.url), "utf8");
  assert.match(page, /URLSearchParams/);
  assert.match(page, /campaign_id/);
  assert.match(page, /activity_type/);
  assert.match(page, /status/);
  assert.match(page, /catch/);
  assert.match(page, /role="alert"/);
  assert.match(page, /navigator\.clipboard\.writeText/);
  assert.match(page, /download/);
});

test("activity record detail has a narrow one-column layout", async () => {
  const styles = await readFile(new URL("../app/globals.css", import.meta.url), "utf8");
  assert.match(styles, /max-width:\s*760px/);
  assert.match(styles, /grid-template-columns:\s*1fr/);
});

test("login sets a signed HttpOnly SameSite cookie", async () => {
  process.env.VIEWER_USERNAME = "admin";
  process.env.VIEWER_PASSWORD = "password";
  process.env.SESSION_SECRET = "test-secret";
  const response = await login(new Request("http://localhost/api/login", { method: "POST", body: JSON.stringify({ username: "admin", password: "password" }), headers: { "content-type": "application/json" } }));
  assert.equal(response.status, 200);
  const cookie = response.headers.get("set-cookie") ?? "";
  assert.match(cookie, /HttpOnly/i);
  assert.match(cookie, /SameSite=Strict/i);
  assert.match(cookie, /Max-Age=28800/i);
});

test("login omits Secure when HTTP deployment explicitly disables it", async () => {
  (process.env as Record<string, string | undefined>).NODE_ENV = "production";
  process.env.VIEWER_COOKIE_SECURE = "false";
  const response = await login(new Request("http://localhost/api/login", { method: "POST", body: JSON.stringify({ username: "admin", password: "password" }), headers: { "content-type": "application/json" } }));
  assert.equal(response.status, 200);
  assert.doesNotMatch(response.headers.get("set-cookie") ?? "", /; Secure/i);
});
