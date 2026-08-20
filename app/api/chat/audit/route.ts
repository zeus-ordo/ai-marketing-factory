import { listChatAuditLogs } from "@/lib/chatbot/audit-log";
import { verifyActorToken } from "@/lib/chatbot/actor-auth";

export async function GET(request: Request) {
  const requiredApiKey = process.env.CHAT_AUDIT_API_KEY;
  const requireAdminToken = (process.env.CHAT_AUDIT_REQUIRE_ADMIN_TOKEN ?? "true").trim().toLowerCase() !== "false";
  if (!requiredApiKey) {
    return Response.json({ detail: "CHAT_AUDIT_API_KEY is not configured" }, { status: 503 });
  }

  const apiKey = request.headers.get("x-chat-audit-key");
  if (apiKey !== requiredApiKey) {
    return Response.json({ detail: "Unauthorized" }, { status: 401 });
  }

  if (requireAdminToken) {
    const actorToken = request.headers.get("x-chat-actor-token") ?? "";
    if (!actorToken) {
      return Response.json({ detail: "Unauthorized" }, { status: 401 });
    }

    let verified: { actorId: string; actorRole: "admin" | "operator" } | null = null;
    try {
      verified = verifyActorToken(actorToken);
    } catch {
      verified = null;
    }
    if (!verified || verified.actorRole !== "admin") {
      return Response.json({ detail: "Unauthorized" }, { status: 401 });
    }
  }

  const url = new URL(request.url);
  const rawLimit = Number(url.searchParams.get("limit") ?? "50");
  const limit = Number.isFinite(rawLimit) ? Math.max(1, Math.min(Math.trunc(rawLimit), 200)) : 50;
  const actorId = url.searchParams.get("actor_id") ?? undefined;
  const actorRoleRaw = url.searchParams.get("actor_role") ?? undefined;
  const actorRole = actorRoleRaw === "admin" || actorRoleRaw === "operator" ? actorRoleRaw : undefined;
  const intent = url.searchParams.get("intent") ?? undefined;

  try {
    const items = await listChatAuditLogs({
      limit,
      actorId,
      actorRole,
      intent,
    });
    return Response.json({ items, total: items.length }, { status: 200 });
  } catch {
    return Response.json({ detail: "Chatbot audit persistence unavailable" }, { status: 503 });
  }
}
