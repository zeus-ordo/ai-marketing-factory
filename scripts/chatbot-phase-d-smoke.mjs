import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { createHmac } from "node:crypto";

const NEXT_BASE_URL = (process.env.CHATBOT_SMOKE_NEXT_BASE_URL ?? "http://localhost:3000").replace(/\/$/, "");
const CAMPAIGN_API_BASE = (
  process.env.CHATBOT_SMOKE_CAMPAIGN_API_BASE ??
  process.env.NEXT_PUBLIC_CAMPAIGN_API_BASE ??
  process.env.NEXT_PUBLIC_API_BASE ??
  "http://localhost:8080"
).replace(/\/$/, "");

const ACTOR_ID = process.env.CHATBOT_SMOKE_ACTOR_ID ?? "chatbot-smoke";
const ACTOR_ROLE = process.env.CHATBOT_SMOKE_ROLE ?? "admin";
const ACTOR_TOKEN_SECRET =
  process.env.CHAT_ACTOR_TOKEN_SECRET ?? process.env.NEXTAUTH_SECRET ?? process.env.JWT_SECRET ?? "";
const AUDIT_API_KEY = process.env.CHAT_AUDIT_API_KEY ?? "change_me_audit_key";

function getAuditHeaders() {
  return {
    "x-user-role": "admin",
    ...(AUDIT_API_KEY ? { "x-chat-audit-key": AUDIT_API_KEY } : {}),
    ...(ACTOR_TOKEN_SECRET ? { "x-chat-actor-token": createActorToken(ACTOR_ID, "admin") } : {}),
  };
}

let context = {};

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

async function chat(message) {
  return chatWithOptions(message, { expectedStatus: 200 });
}

async function chatWithOptions(message, options) {
  const expectedStatuses = options?.expectedStatuses ?? [options?.expectedStatus ?? 200];
  const useActorToken = options?.useActorToken ?? true;
  const headers = {
    "Content-Type": "application/json",
    ...(useActorToken && ACTOR_TOKEN_SECRET
      ? { "x-chat-actor-token": createActorToken(ACTOR_ID, ACTOR_ROLE) }
      : {}),
  };

  const response = await fetch(`${NEXT_BASE_URL}/api/chat/execute`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      message,
      locale: "en",
      context,
    }),
  });
  const payload = await response.json();
  if (!expectedStatuses.includes(response.status)) {
    throw new Error(`Chat failed (${response.status}): ${JSON.stringify(payload)}`);
  }
  if (!response.ok) return payload;
  context = payload.context;
  return payload;
}

async function uploadReference(campaignId) {
  const tempFilePath = path.join(os.tmpdir(), `chatbot-smoke-${Date.now()}.txt`);
  await fs.writeFile(tempFilePath, "chatbot phase d smoke reference\n", "utf-8");

  const formData = new FormData();
  const content = await fs.readFile(tempFilePath);
  const file = new File([content], "chatbot-smoke-ref.txt", { type: "text/plain" });
  formData.set("file", file);
  formData.set("operator", ACTOR_ID);

  const response = await fetch(`${CAMPAIGN_API_BASE}/api/v1/campaigns/${campaignId}/references/upload`, {
    method: "POST",
    body: formData,
  });

  await fs.unlink(tempFilePath).catch(() => {});

  const payload = await response.json();
  if (!response.ok) {
    throw new Error(`Reference upload failed (${response.status}): ${JSON.stringify(payload)}`);
  }
  return payload;
}

async function getAuditLogs() {
  return getAuditLogsWithOptions({ expectedStatus: 200, withApiKey: true });
}

async function getAuditLogsWithOptions(options) {
  const expectedStatus = options?.expectedStatus ?? 200;
  const withApiKey = options?.withApiKey ?? true;
  const response = await fetch(`${NEXT_BASE_URL}/api/chat/audit?limit=50`, {
    method: "GET",
    headers: withApiKey ? getAuditHeaders() : {},
  });
  const payload = await response.json();
  if (response.status !== expectedStatus) {
    throw new Error(`Audit query failed (${response.status}): ${JSON.stringify(payload)}`);
  }
  if (!response.ok) return payload;
  return payload.items ?? [];
}

async function getTraceHealthWithOptions(options) {
  const expectedStatuses = options?.expectedStatuses ?? [options?.expectedStatus ?? 200];
  const withActorToken = options?.withActorToken ?? false;
  const response = await fetch(`${NEXT_BASE_URL}/api/system/trace/health`, {
    method: "GET",
    headers: withActorToken && ACTOR_TOKEN_SECRET ? { "x-chat-actor-token": createActorToken(ACTOR_ID, "admin") } : {},
  });
  const contentType = response.headers.get("content-type") ?? "";
  const payload = contentType.includes("application/json")
    ? await response.json()
    : { detail: (await response.text()).slice(0, 200) };
  if (!expectedStatuses.includes(response.status)) {
    throw new Error(`Trace health query failed (${response.status}): ${JSON.stringify(payload)}`);
  }
  return payload;
}

function createActorToken(actorId, actorRole) {
  if (!ACTOR_TOKEN_SECRET) {
    throw new Error("Missing CHAT_ACTOR_TOKEN_SECRET (or NEXTAUTH_SECRET/JWT_SECRET)");
  }
  const payload = {
    actor_id: actorId,
    actor_role: actorRole,
    exp: Date.now() + 5 * 60 * 1000,
  };
  const payloadEncoded = Buffer.from(JSON.stringify(payload), "utf-8").toString("base64url");
  const signature = createHmac("sha256", ACTOR_TOKEN_SECRET).update(payloadEncoded).digest("base64url");
  return `${payloadEncoded}.${signature}`;
}

async function main() {
  console.log("[smoke] negative: high-risk without actor token should fail");
  const negativeHighRisk = await chatWithOptions("delete reference ref_fake for campaign cmp_fake", {
    expectedStatuses: [401, 403],
    useActorToken: false,
  });
  assert(
    negativeHighRisk.detail?.includes("Actor token required") || negativeHighRisk.detail?.includes("Admin role required"),
    "unauth high-risk should be blocked",
  );

  console.log("[smoke] negative: audit read without key should fail");
  const negativeAudit = await getAuditLogsWithOptions({ expectedStatus: 401, withApiKey: false });
  assert(negativeAudit.detail?.includes("Unauthorized"), "audit endpoint should require api key");

  console.log("[smoke] negative: trace health without actor token should fail");
  const negativeTraceHealth = await getTraceHealthWithOptions({ expectedStatuses: [401, 404], withActorToken: false });
  if (negativeTraceHealth?.detail && typeof negativeTraceHealth.detail === "string") {
    const detail = negativeTraceHealth.detail;
    assert(
      detail.includes("Unauthorized") || detail.includes("Not Found") || detail.includes("<!DOCTYPE"),
      "trace health endpoint should be protected or unavailable",
    );
  }

  console.log("[smoke] create campaign");
  const create = await chat("create campaign named Chatbot Phase D Smoke budget 50000");
  assert(create.actionResult?.ok, "create campaign should succeed");
  const campaignId = create.actionResult?.campaign_id;
  assert(typeof campaignId === "string" && campaignId.startsWith("cmp_"), "campaign_id should be present");

  console.log("[smoke] run campaign");
  const run = await chat(`run campaign ${campaignId}`);
  assert(run.actionResult?.ok, "run campaign should succeed");

  console.log("[smoke] list tasks");
  const tasks = await chat(`list tasks for campaign ${campaignId}`);
  assert(tasks.intent === "list_tasks", "list tasks intent expected");

  console.log("[smoke] list validation results");
  const validation = await chat(`show validation results for campaign ${campaignId}`);
  assert(validation.intent === "list_validation_results", "validation intent expected");

  console.log("[smoke] list review queue");
  const review = await chat("show review queue");
  assert(review.intent === "list_review_queue", "review queue intent expected");

  console.log("[smoke] upload reference (prep)");
  const uploaded = await uploadReference(campaignId);
  assert(uploaded.reference_id?.startsWith("ref_"), "uploaded reference id expected");
  const referenceId = uploaded.reference_id;

  console.log("[smoke] list references");
  const references = await chat(`show references for campaign ${campaignId}`);
  assert(references.intent === "list_references", "list references intent expected");

  console.log("[smoke] stage delete reference");
  const stageDelete = await chat(`delete reference ${referenceId} for campaign ${campaignId}`);
  assert(stageDelete.intent === "delete_reference", "delete reference intent expected");
  const deleteNonce = stageDelete.context?.pendingAction?.nonce;
  assert(typeof deleteNonce === "string" && deleteNonce.length >= 4, "delete confirmation nonce expected");

  console.log("[smoke] confirm delete reference");
  const confirmDelete = await chat(`confirm ${deleteNonce}`);
  assert(confirmDelete.actionResult?.ok, "confirm delete should succeed");

  const pendingReview = (review.actionResult?.reviewItems ?? []).find((item) => item.status === "review_pending");
  const reviewId = pendingReview?.review_id;
  if (typeof reviewId === "string" && reviewId.length > 0) {
    console.log("[smoke] stage approve review");
    const stageApprove = await chat(`approve review ${reviewId}`);
    assert(stageApprove.intent === "approve_review", "approve review intent expected");
    const approveNonce = stageApprove.context?.pendingAction?.nonce;
    assert(typeof approveNonce === "string" && approveNonce.length >= 4, "approve confirmation nonce expected");

    console.log("[smoke] confirm approve review");
    const confirmApprove = await chat(`confirm ${approveNonce}`);
    if (!confirmApprove.actionResult?.ok) {
      throw new Error(`confirm approve should succeed: ${JSON.stringify(confirmApprove)}`);
    }
  } else {
    console.log("[smoke] no review_pending item, skip approve flow");
  }

  console.log("[smoke] audit logs");
  const auditItems = await getAuditLogs();
  assert(Array.isArray(auditItems), "audit items should be array");
  const hasConfirm = auditItems.some((item) => item.intent === "confirm_pending_action");
  assert(hasConfirm, "audit should include confirm_pending_action");

  console.log("[smoke] PASS");
}

main().catch((error) => {
  console.error("[smoke] FAIL", error);
  process.exit(1);
});
