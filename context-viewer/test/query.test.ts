import assert from "node:assert/strict";
import test from "node:test";

import { buildContextListQuery, redactSecrets } from "../lib/query.ts";
import { isValidSession, signSession } from "../lib/session.ts";

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

test("redactSecrets removes secret-looking JSON values but preserves ordinary prompt text", () => {
  const result = redactSecrets({
    prompt: "Write a launch email for our token rewards program.",
    api_key: "do-not-return",
    nested: { authorization: "Bearer do-not-return", audience: "customers" },
    items: [{ password: "hidden" }, { text: "ordinary context" }],
  });

  assert.equal(result.prompt, "Write a launch email for our token rewards program.");
  assert.equal(result.api_key, "[REDACTED]");
  assert.equal(result.nested.authorization, "[REDACTED]");
  assert.equal(result.nested.audience, "customers");
  assert.equal(result.items[0].password, "[REDACTED]");
  assert.equal(result.items[1].text, "ordinary context");
});

test("invalid or absent session cookies are rejected", () => {
  assert.equal(isValidSession(undefined, "test-secret"), false);
  assert.equal(isValidSession("not-a-session", "test-secret"), false);
  assert.equal(isValidSession(`${signSession("admin", "test-secret")}tampered`, "test-secret"), false);
});
