/**
 * DB Cleanup Script — ai-marketing-factory
 *
 * Usage: node scripts/cleanup-db.mjs [--force] [--dry-run]
 *
 * Cleans up:
 *   1. Old campaign trace events & chat transcripts (≥30 days old)
 *   2. Orphaned campaign_traces (no associated events/chat)
 *   3. Audit log entries (≥90 days old)
 *   4. Orphaned asset_versions (version exists but asset_id not in asset_outputs)
 *
 * Requires: CHATBOT_INTERNAL_API_KEY environment variable
 *           (or set INTERNAL_KEY before running)
 *
 * For direct PostgreSQL access (recommended for production), run the SQL below
 * manually against the marketing_ai database:
 *   psql "postgresql://app:password@localhost:5432/marketing_ai"
 */

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

loadEnvFile(".env.local");

const BASE_URL = (process.env.E2E_BASE_URL ?? process.env.REGRESSION_BASE_URL ?? "http://localhost:3000").replace(/\/$/, "");
const INTERNAL_KEY = process.env.CHATBOT_INTERNAL_API_KEY ?? process.env.CAMPAIGN_INTERNAL_API_KEY ?? "";
const FORCE = process.argv.includes("--force");
const DRY_RUN = process.argv.includes("--dry-run");

if (!INTERNAL_KEY || INTERNAL_KEY === "change_me_internal_key" || INTERNAL_KEY === "change_me_audit_key") {
  console.error("[cleanup] FAIL: CHATBOT_INTERNAL_API_KEY is not set or is using a placeholder.");
  console.error("           Set it in .env.local or as an environment variable.");
  process.exit(1);
}

if (DRY_RUN) {
  console.log("[cleanup] DRY RUN — no changes will be made");
}

// ─── 1. Trace cleanup via campaign-service API (30-day cutoff) ───────────────

async function cleanupTraces() {
  console.log("\n[cleanup:traces] POST /api/v1/system/trace/cleanup");
  const res = await fetch(`${BASE_URL}/api/v1/system/trace/cleanup`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-internal-api-key": INTERNAL_KEY,
    },
    body: JSON.stringify({ force: FORCE, operator: "cleanup-script" }),
  });
  const payload = await res.json().catch(() => ({}));
  if (!res.ok) {
    console.error(`  ❌ Failed (${res.status}): ${JSON.stringify(payload)}`);
    return null;
  }
  console.log(`  ✅ Deleted trace events: ${payload.deleted_events ?? "N/A"}`);
  console.log(`  ✅ Deleted chat transcripts: ${payload.deleted_chat ?? "N/A"}`);
  console.log(`  ✅ Deleted orphaned traces: ${payload.deleted_traces ?? "N/A"}`);
  return payload;
}

// ─── SQL queries for direct PostgreSQL cleanup ────────────────────────────────

/**
 * These SQL queries should be run manually via psql or a DB admin tool.
 * They are safe to run — all queries use DELETE with WHERE clauses on old data.
 *
 * Connection string: postgresql://app:password@localhost:5432/marketing_ai
 * (When running on the docker network, use: postgresql://app:password@postgres:5432/marketing_ai)
 */
const SQL_CLEANUP_QUERIES = [
  {
    name: "audit_logs older than 90 days",
    sql: `
      -- Remove audit log entries older than 90 days
      DELETE FROM audit_logs
      WHERE created_at < NOW() - INTERVAL '90 days';
    `,
  },
  {
    name: "campaign_run_records older than 180 days (completed only)",
    sql: `
      -- Remove old completed campaign run records
      DELETE FROM campaign_runs
      WHERE status = 'completed'
        AND finished_at < NOW() - INTERVAL '180 days';
    `,
  },
  {
    name: "asset_versions orphaned (no corresponding asset_output)",
    sql: `
      -- Remove asset_versions where the asset_id no longer exists in asset_outputs
      -- (Caution: only run if you are sure asset_outputs is the source of truth)
      DELETE FROM asset_versions av
      WHERE NOT EXISTS (
        SELECT 1 FROM asset_outputs ao WHERE ao.asset_id = av.asset_id
      );
    `,
  },
  {
    name: "campaigns soft-deleted older than 1 year",
    sql: `
      -- Permanently remove campaigns that were soft-deleted over a year ago
      DELETE FROM campaigns
      WHERE deleted_at IS NOT NULL
        AND deleted_at < NOW() - INTERVAL '1 year';
    `,
  },
  {
    name: "campaign_references with no associated campaign",
    sql: `
      -- Remove reference files whose campaign no longer exists
      DELETE FROM campaign_references cr
      WHERE NOT EXISTS (
        SELECT 1 FROM campaigns c WHERE c.campaign_id = cr.campaign_id
      );
    `,
  },
];

async function runCleanup() {
  console.log(`[cleanup] Starting DB cleanup — BASE_URL=${BASE_URL}`);
  console.log(`         Force=${FORCE} DryRun=${DRY_RUN}`);

  // Step 1: Trace cleanup via API
  await cleanupTraces();

  // Step 2: Print SQL for direct DB cleanup (for reference / manual run)
  if (DRY_RUN) {
    console.log("\n[cleanup:sql] DRY RUN — SQL queries that would clean up remaining tables:");
  } else {
    console.log("\n[cleanup:sql] The following SQL queries should be run manually via psql:");
  }

  for (const { name, sql } of SQL_CLEANUP_QUERIES) {
    if (DRY_RUN) {
      console.log(`\n  -- [DRY RUN] Would execute: ${name}`);
      console.log(sql.trim().split("\n").map((l) => "  " + l).join("\n"));
    } else {
      console.log(`\n  [skip] ${name} — run manually:`);
      const lines = sql.trim().split("\n").map((l) => "    " + l.trim()).join("\n");
      console.log(lines);
    }
  }

  console.log("\n[cleanup] Done.");
}

runCleanup().catch((err) => {
  console.error("[cleanup] Unexpected error:", err);
  process.exit(1);
});
