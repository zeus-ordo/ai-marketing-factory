import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { buildContextDetailQuery, buildContextListQuery, redactSecrets } from "../lib/query.ts";
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
