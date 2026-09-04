import assert from "node:assert/strict";
import { findSecretIssues } from "./check-secrets.mjs";

const weakPassword = ["db", "password"].join("-");
const providerKey = ["hardcoded", "provider", "key"].join("-");
const unsafeFallback = ["embedded", "fallback", "secret"].join("-");
const unsafeToken = ["embedded", "token", "value"].join("-");
const safeFallback = ["change", "me"].join("_");
const issues = findSecretIssues([
  ["fixture.env", `DATABASE_URL=postgresql://app:${weakPassword}@db/marketing`],
  ["fixture.bat", `set MINIMAX_API_KEY=${providerKey}`],
  ["fixture.yml", `JWT_SECRET: ${"${JWT_SECRET:-"}${unsafeFallback}}`],
  ["fixture.env", `COMBINED_API_KEY=${"${SAFE_KEY-safe}"}${"${UNSAFE_KEY-"}${unsafeToken}}`],
  ["fixture.sh", `export CHAT_AUDIT_API_KEY='${providerKey}'`],
  ["fixture.py", `API_TOKEN = '${unsafeToken}'`],
  ["fixture.js", `const API_KEY = '${providerKey}'`],
  ["fixture-safe.yml", `JWT_SECRET: ${"${JWT_SECRET:-"}${safeFallback}}`],
  ["fixture-safe.env", "EXTERNAL_SEARCH_API_KEY=${EXTERNAL_SEARCH_API_KEY}"],
  ["fixture-safe.ps1", "$env:JWT_SECRET = $env:JWT_SECRET"],
], new Set(["fixture.env", "fixture.bat", "fixture.yml", "fixture.sh", "fixture.py", "fixture.js", "fixture-safe.yml", "fixture-safe.env", "fixture-safe.ps1"]));

assert.deepEqual(issues.map(({ file, key }) => `${file}:${key}`), [
  "fixture.env:dsn-credential",
  "fixture.bat:MINIMAX_API_KEY",
  "fixture.yml:JWT_SECRET",
  "fixture.env:COMBINED_API_KEY",
  "fixture.sh:CHAT_AUDIT_API_KEY",
  "fixture.py:API_TOKEN",
  "fixture.js:API_KEY",
]);
assert.ok(issues.every(({ value }) => value === undefined));
console.log("secret scanner contract passed");
