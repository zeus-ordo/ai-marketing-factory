import { createHmac, timingSafeEqual } from "node:crypto";
import { detectIntentLLM } from "@/lib/chatbot/intents";
import { executeChatCommand } from "@/lib/chatbot/commands";
import { appendChatAuditLog, type ChatActorRole } from "@/lib/chatbot/audit-log";
import { verifyPendingActionToken } from "@/lib/chatbot/pending-action";
import { verifyActorToken } from "@/lib/chatbot/actor-auth";
import { sanitizeChatText, sanitizeChatTexts } from "@/lib/chatbot/sanitize";
import { supportedLocales, type SupportedLocale } from "@/lib/i18n/translations";
import type { ChatContext, ChatExecuteRequest, ChatIntent } from "@/lib/types/chatbot";

export async function POST(request: Request) {
  let parsedPayload: unknown;
  try {
    parsedPayload = await request.json();
  } catch {
    return Response.json({ detail: "Invalid JSON body" }, { status: 400 });
  }

  if (!isObject(parsedPayload)) {
    return Response.json({ detail: "Request body must be an object" }, { status: 400 });
  }

  const payload = parsedPayload as ChatExecuteRequest;

  if (typeof payload.message !== "string") {
    return Response.json({ detail: "message must be a string" }, { status: 400 });
  }

  const message = sanitizeChatText(payload.message).trim();
  if (message.length === 0) {
    return Response.json({ detail: "message is required" }, { status: 400 });
  }

  const locale = detectMessageLocale(message) ?? normalizeLocale(payload.locale);
  const context = normalizeContext(payload.context);
  const detection = await detectIntentLLM(message, context);
  const actor = resolveActor(request.headers);

  if (isMutatingIntent(detection.intent) && actor.id === "anonymous") {
    await appendRejectionAuditLog({
      actor,
      locale,
      message,
      intent: detection.intent,
      detail: "missing_actor_token",
      context,
    });
    return Response.json({ detail: "Actor token required for mutating action" }, { status: 401 });
  }

  if (isHighRiskIntent(detection.intent, context) && actor.role !== "admin") {
    await appendRejectionAuditLog({
      actor,
      locale,
      message,
      intent: detection.intent,
      detail: "admin_role_required",
      context,
    });
    return Response.json({ detail: "Admin role required for high-risk action" }, { status: 403 });
  }

  const result = await executeChatCommand({
    locale,
    detection,
    context,
    message,
  });
  const sanitizedResult = {
    ...result,
    reply: sanitizeChatText(result.reply),
    followUp: sanitizeChatTexts(result.followUp),
  };

  // Fire-and-forget: audit log must never block the chat response
  const auditPromise = appendChatAuditLog({
    actorId: actor.id,
    actorRole: actor.role,
    locale,
    message,
    intent: sanitizedResult.intent,
    ok: sanitizedResult.actionResult.ok,
    detail: sanitizedResult.actionResult.detail,
    requestContext: context,
    resultContext: sanitizedResult.context,
  });
  auditPromise.catch((err) => {
    console.error("[chat/execute] audit log write failed:", err instanceof Error ? err.message : String(err));
  });

  const campaignId =
    sanitizedResult.actionResult.campaign_id ?? sanitizedResult.context.activeCampaignId ?? sanitizedResult.context.lastCampaignId;
  if (campaignId) {
    const maskedUserMessage = maskChatText(message);
    const maskedAssistantReply = maskChatText(sanitizedResult.reply);

    void appendCampaignTraceEvent(campaignId, {
      event_type: "chat_message",
      actor_id: actor.id,
      actor_role: actor.role,
      summary: "User chat message",
      source: "chatbot",
      payload: {
        role: "user",
        content_masked: maskedUserMessage,
      },
    });

    void appendCampaignTraceEvent(campaignId, {
      event_type: "chat_message",
      actor_id: actor.id,
      actor_role: actor.role,
      summary: "Assistant chat message",
      source: "chatbot",
      payload: {
        role: "assistant",
        content_masked: maskedAssistantReply,
      },
    });
  }

  return Response.json(sanitizedResult, { status: 200 });
}

function normalizeLocale(locale?: string): SupportedLocale {
  if (!locale) return "en";

  const normalized = locale.trim();
  const lower = normalized.toLowerCase();
  if (lower.startsWith("zh")) return "zh-Hant";
  if (lower.startsWith("ja")) return "ja";
  if (lower.startsWith("en")) return "en";

  if (supportedLocales.includes(normalized as SupportedLocale)) {
    return normalized as SupportedLocale;
  }

  return "en";
}

function detectMessageLocale(message: string): SupportedLocale | null {
  const text = message.trim();
  if (!text) return null;

  // Japanese has dedicated kana ranges; check these before Han characters.
  if (/[\u3040-\u30ff\u31f0-\u31ff]/.test(text)) return "ja";

  // CJK Han characters usually indicate Traditional Chinese in this product's supported locale set.
  if (/[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]/.test(text)) return "zh-Hant";

  // Latin alphabet defaults to English.
  if (/[a-z]/i.test(text)) return "en";

  return null;
}

function normalizeContext(value: unknown): ChatContext {
  if (!isObject(value)) return {};

  const nextContext: ChatContext = {};
  if (typeof value.activeCampaignId === "string" && isCampaignId(value.activeCampaignId)) {
    nextContext.activeCampaignId = value.activeCampaignId;
  }
  if (typeof value.lastCampaignId === "string" && isCampaignId(value.lastCampaignId)) {
    nextContext.lastCampaignId = value.lastCampaignId;
  }
  if (typeof value.pendingActionToken === "string") {
    const verified = verifyPendingActionToken(value.pendingActionToken);
    if (verified) {
      nextContext.pendingActionToken = value.pendingActionToken;
      nextContext.pendingAction = verified;
    } else {
      // Token was provided but could not be verified (expired or tampered)
      nextContext.pendingActionTokenExpired = true;
    }
  }
  if (isObject(value.draftBrief)) {
    nextContext.draftBrief = value.draftBrief as ChatContext["draftBrief"];
  }
  if (Array.isArray(value.awaitingBriefFields)) {
    const fields = value.awaitingBriefFields.filter((item): item is string => typeof item === "string" && item.trim().length > 0);
    if (fields.length > 0) nextContext.awaitingBriefFields = fields;
  }
  if (typeof value.briefConfidence === "number" && Number.isFinite(value.briefConfidence)) {
    nextContext.briefConfidence = value.briefConfidence;
  }
  return nextContext;
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isCampaignId(value: string): boolean {
  return /^cmp_[a-zA-Z0-9]+$/.test(value);
}

function resolveActor(headers: Headers): { id: string; role: ChatActorRole } {
  const actorToken = headers.get("x-chat-actor-token") ?? "";
  if (actorToken) {
    let verified: { actorId: string; actorRole: ChatActorRole } | null = null;
    try {
      verified = verifyActorToken(actorToken);
    } catch {
      verified = null;
    }
    if (verified) {
      return {
        id: verified.actorId,
        role: verified.actorRole,
      };
    }
  }

  const jwtActor = resolveJwtActor(headers.get("authorization") ?? "");
  if (jwtActor) return jwtActor;

  return {
    id: "anonymous",
    role: "operator",
  };
}

function resolveJwtActor(authorization: string): { id: string; role: ChatActorRole } | null {
  if (!authorization.startsWith("Bearer ")) return null;
  const token = authorization.slice("Bearer ".length).trim();
  const [headerEncoded, payloadEncoded, signature] = token.split(".");
  if (!headerEncoded || !payloadEncoded || !signature) return null;

  const secret = process.env.JWT_SECRET;
  if (!secret) return null;

  const expectedSignature = createHmac("sha256", secret).update(`${headerEncoded}.${payloadEncoded}`).digest("base64url");
  const actual = Buffer.from(signature);
  const expected = Buffer.from(expectedSignature);
  if (actual.length !== expected.length || !timingSafeEqual(actual, expected)) return null;

  try {
    const payload = JSON.parse(Buffer.from(payloadEncoded, "base64url").toString("utf-8")) as {
      sub?: string;
      permissions?: string[];
      exp?: number;
    };
    if (!payload.sub) return null;
    if (typeof payload.exp === "number" && Date.now() >= payload.exp * 1000) return null;
    const permissions = Array.isArray(payload.permissions) ? payload.permissions : [];
    const role: ChatActorRole = permissions.some((item) => ["*", "platform:*", "platform:admin", "review:*"].includes(item)) ? "admin" : "operator";
    return { id: payload.sub, role };
  } catch {
    return null;
  }
}

function isHighRiskIntent(intent: string, context: ChatContext): boolean {
  if (intent === "confirm_pending_action") {
    return context.pendingAction?.type === "delete_reference" || context.pendingAction?.type === "approve_review";
  }
  return intent === "delete_reference" || intent === "approve_review";
}

function isMutatingIntent(intent: string): boolean {
  return (
    intent === "create_campaign" ||
    intent === "run_campaign" ||
    intent === "delete_reference" ||
    intent === "approve_review" ||
    intent === "confirm_pending_action"
  );
}

async function appendRejectionAuditLog(params: {
  actor: { id: string; role: ChatActorRole };
  locale: SupportedLocale;
  message: string;
  intent: string;
  detail: string;
  context: ChatContext;
}): Promise<void> {
  try {
    await appendChatAuditLog({
      actorId: params.actor.id,
      actorRole: params.actor.role,
      locale: params.locale,
      message: params.message,
      intent: params.intent as ChatIntent,
      ok: false,
      detail: params.detail,
      requestContext: params.context,
      resultContext: params.context,
    });
  } catch {
    // keep authorization semantics unchanged even if audit sink fails
  }
}

function maskChatText(value: string): string {
  const condensed = value.replace(/\s+/g, " ").trim();
  const redactedEmail = condensed.replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi, "[redacted-email]");
  const redactedLongToken = redactedEmail.replace(/[A-Za-z0-9_-]{24,}/g, "[redacted-token]");
  if (redactedLongToken.length <= 220) return redactedLongToken;
  return `${redactedLongToken.slice(0, 220)}…`;
}

async function appendCampaignTraceEvent(
  campaignId: string,
  payload: {
    event_type: string;
    actor_id: string;
    actor_role: string;
    summary: string;
    source: string;
    payload: Record<string, unknown>;
  },
): Promise<void> {
  const apiBase =
    process.env.CAMPAIGN_API_BASE ??
    process.env.NEXT_PUBLIC_CAMPAIGN_API_BASE ??
    process.env.NEXT_PUBLIC_API_BASE ??
    "http://localhost:8080";
  const internalApiKey = process.env.CHATBOT_INTERNAL_API_KEY ?? "";
  if (!internalApiKey) return;

  try {
    const response = await fetch(`${apiBase.replace(/\/$/, "")}/api/v1/campaigns/${campaignId}/trace/events`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-internal-api-key": internalApiKey,
      },
      body: JSON.stringify(payload),
      cache: "no-store",
    });
    if (!response.ok) {
      throw new Error(`trace append failed: ${response.status}`);
    }
  } catch {
    // no-op: trace append is best effort for chat flow
  }
}
