import { randomUUID } from "node:crypto";
import type { ChatContext, ChatIntent } from "@/lib/types/chatbot";
import type { SupportedLocale } from "@/lib/i18n/translations";

export type ChatActorRole = "admin" | "operator";

export type ChatAuditRecord = {
  audit_id: string;
  timestamp: string;
  actor_id: string;
  actor_role: ChatActorRole;
  locale: SupportedLocale;
  message: string;
  intent: ChatIntent;
  ok: boolean;
  detail?: string;
  request_pending_action_type?: string;
  request_pending_campaign_id?: string;
  request_pending_reference_id?: string;
  request_pending_review_id?: string;
  result_pending_action_type?: string;
  result_pending_campaign_id?: string;
  result_pending_reference_id?: string;
  result_pending_review_id?: string;
};

const FALLBACK_MAX = 500;
const fallbackAuditLogs: ChatAuditRecord[] = [];

function shouldRequirePersistentAudit(): boolean {
  const raw = (process.env.CHAT_AUDIT_REQUIRE_PERSISTENCE ?? "false").trim().toLowerCase();
  return raw !== "false";
}

export async function appendChatAuditLog(input: {
  actorId: string;
  actorRole: ChatActorRole;
  locale: SupportedLocale;
  message: string;
  intent: ChatIntent;
  ok: boolean;
  detail?: string;
  requestContext: ChatContext;
  resultContext: ChatContext;
}) {
  const record: ChatAuditRecord = {
    audit_id: `chat_audit_${randomUUID()}`,
    timestamp: new Date().toISOString(),
    actor_id: input.actorId,
    actor_role: input.actorRole,
    locale: input.locale,
    message: input.message,
    intent: input.intent,
    ok: input.ok,
    detail: input.detail,
    request_pending_action_type: input.requestContext.pendingAction?.type,
    request_pending_campaign_id: input.requestContext.pendingAction?.campaignId,
    request_pending_reference_id: input.requestContext.pendingAction?.referenceId,
    request_pending_review_id: input.requestContext.pendingAction?.reviewId,
    result_pending_action_type: input.resultContext.pendingAction?.type,
    result_pending_campaign_id: input.resultContext.pendingAction?.campaignId,
    result_pending_reference_id: input.resultContext.pendingAction?.referenceId,
    result_pending_review_id: input.resultContext.pendingAction?.reviewId,
  };

  try {
    const apiBase = getCampaignApiBase();
    const internalApiKey = process.env.CHATBOT_INTERNAL_API_KEY ?? "";
    if (!internalApiKey) {
      throw new Error("Missing CHATBOT_INTERNAL_API_KEY for chatbot audit write");
    }
    const response = await fetch(`${apiBase}/api/v1/chatbot/audit-logs`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(internalApiKey ? { "x-internal-api-key": internalApiKey } : {}),
      },
      body: JSON.stringify(record),
      cache: "no-store",
    });
    if (!response.ok) {
      throw new Error(`audit write failed: ${response.status}`);
    }
  } catch {
    if (shouldRequirePersistentAudit()) {
      throw new Error("Persistent chatbot audit log write failed");
    }
    fallbackAuditLogs.unshift(record);
    if (fallbackAuditLogs.length > FALLBACK_MAX) {
      fallbackAuditLogs.length = FALLBACK_MAX;
    }
  }

  return record;
}

export async function listChatAuditLogs(params: {
  limit: number;
  actorId?: string;
  actorRole?: ChatActorRole;
  intent?: string;
}): Promise<ChatAuditRecord[]> {
  const safeLimit = Math.max(1, Math.min(params.limit, 200));
  const query = new URLSearchParams({ limit: String(safeLimit) });
  if (params.actorId) query.set("actor_id", params.actorId);
  if (params.actorRole) query.set("actor_role", params.actorRole);
  if (params.intent) query.set("intent", params.intent);

  try {
    const apiBase = getCampaignApiBase();
    const internalApiKey = process.env.CHATBOT_INTERNAL_API_KEY ?? "";
    if (!internalApiKey) {
      throw new Error("Missing CHATBOT_INTERNAL_API_KEY for chatbot audit read");
    }
    const response = await fetch(`${apiBase}/api/v1/chatbot/audit-logs?${query.toString()}`, {
      method: "GET",
      headers: {
        ...(internalApiKey ? { "x-internal-api-key": internalApiKey } : {}),
      },
      cache: "no-store",
    });
    if (!response.ok) {
      throw new Error(`Request failed: ${response.status}`);
    }
    const data = (await response.json()) as { items?: ChatAuditRecord[] };
    return Array.isArray(data.items) ? data.items : [];
  } catch {
    if (shouldRequirePersistentAudit()) {
      throw new Error("Persistent chatbot audit log query failed");
    }

    return fallbackAuditLogs
      .filter((item) => {
        if (params.actorId && item.actor_id !== params.actorId) return false;
        if (params.actorRole && item.actor_role !== params.actorRole) return false;
        if (params.intent && item.intent !== params.intent) return false;
        return true;
      })
      .slice(0, safeLimit);
  }
}

function getCampaignApiBase(): string {
  const base =
    process.env.CAMPAIGN_API_BASE ??
    process.env.NEXT_PUBLIC_CAMPAIGN_API_BASE ??
    process.env.NEXT_PUBLIC_API_BASE ??
    "http://localhost:8080";
  if (base === "/") return "http://campaign-service:8080";
  return base.replace(/\/$/, "");
}
