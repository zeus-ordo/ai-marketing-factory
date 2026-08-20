import { verifyActorToken } from "@/lib/chatbot/actor-auth";

export function getCampaignApiBase(): string {
  const base =
    process.env.CAMPAIGN_API_BASE ??
    process.env.NEXT_PUBLIC_CAMPAIGN_API_BASE ??
    process.env.NEXT_PUBLIC_API_BASE ??
    "http://localhost:8080";
  if (base === "/") {
    return typeof window === "undefined" ? "http://campaign-service:8080" : "";
  }
  return base.replace(/\/$/, "");
}

export function getInternalApiKeyOrThrow(): string {
  const key = process.env.CHATBOT_INTERNAL_API_KEY ?? "";
  if (!key) {
    throw new Error("CHATBOT_INTERNAL_API_KEY is not configured");
  }
  return key;
}

export function resolveTraceActorFromRequest(request: Request): { actorId: string; actorRole: "admin" | "operator" } | null {
  const cookieHeader = request.headers.get("cookie") ?? "";
  const cookieToken = parseCookie(cookieHeader, "chat_actor_token");
  const headerToken = request.headers.get("x-chat-actor-token") ?? "";

  const token = headerToken || cookieToken;
  if (!token) return null;

  let verified: { actorId: string; actorRole: "admin" | "operator" } | null = null;
  try {
    verified = verifyActorToken(token);
  } catch {
    return null;
  }
  if (!verified) return null;
  return {
    actorId: verified.actorId,
    actorRole: verified.actorRole,
  };
}

export async function fetchWithTimeout(
  url: string,
  init?: RequestInit & { timeoutMs?: number },
): Promise<Response> {
  const timeoutMs = init?.timeoutMs ?? 30_000;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, { ...init, signal: controller.signal });
    clearTimeout(timer);
    return response;
  } catch (err) {
    clearTimeout(timer);
    if (err instanceof Error && err.name === "AbortError") {
      throw new Error(`Request timed out after ${timeoutMs / 1000}s`);
    }
    throw err;
  }
}

function parseCookie(cookie: string, name: string): string {
  const target = `${name}=`;
  const parts = cookie.split(";");
  for (const rawPart of parts) {
    const part = rawPart.trim();
    if (part.startsWith(target)) {
      return decodeURIComponent(part.slice(target.length));
    }
  }
  return "";
}
