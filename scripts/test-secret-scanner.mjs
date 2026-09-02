import assert from "node:assert/strict";
import { findSecretIssues } from "./check-secrets.mjs";

const issues = findSecretIssues([
  ["fixture.env", "DATABASE_URL=postgresql://app:db-password@db/marketing"],
  ["fixture.bat", "set MINIMAX_API_KEY=hardcoded-provider-key"],
  ["fixture.yml", "JWT_SECRET: ${JWT_SECRET:-embedded-fallback-secret}"],
  ["fixture.ps1", "$env:API_TOKEN = 'embedded-token-value'"],
  ["fixture-safe.yml", "JWT_SECRET: ${JWT_SECRET:-change_me}"],
  ["fixture-safe.env", "EXTERNAL_SEARCH_API_KEY=${EXTERNAL_SEARCH_API_KEY}"],
  ["fixture-safe.ps1", "$env:JWT_SECRET = $env:JWT_SECRET"],
], new Set(["fixture.env", "fixture.bat", "fixture.yml", "fixture.ps1", "fixture-safe.yml", "fixture-safe.env"]));

assert.deepEqual(issues.map(({ file, key }) => `${file}:${key}`), [
  "fixture.env:dsn-credential",
  "fixture.bat:MINIMAX_API_KEY",
  "fixture.yml:JWT_SECRET",
  "fixture.ps1:API_TOKEN",
]);
assert.ok(issues.every(({ value }) => value === undefined));
console.log("secret scanner contract passed");
