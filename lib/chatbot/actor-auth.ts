import { createHmac, timingSafeEqual } from "node:crypto";

export type ActorRole = "admin" | "operator";

type ActorTokenPayload = {
  actor_id: string;
  actor_role: ActorRole;
  exp: number;
};

export function verifyActorToken(token: string): { actorId: string; actorRole: ActorRole } | null {
  const [payloadEncoded, signature] = token.split(".");
  if (!payloadEncoded || !signature) return null;

  const expectedSignature = sign(payloadEncoded);
  const actual = Buffer.from(signature);
  const expected = Buffer.from(expectedSignature);
  if (actual.length !== expected.length) return null;
  if (!timingSafeEqual(actual, expected)) return null;

  try {
    const payload = JSON.parse(Buffer.from(payloadEncoded, "base64url").toString("utf-8")) as ActorTokenPayload;
    if (!isValidPayload(payload)) return null;
    if (Date.now() > payload.exp) return null;

    return {
      actorId: payload.actor_id,
      actorRole: payload.actor_role,
    };
  } catch {
    return null;
  }
}

function sign(payloadEncoded: string): string {
  const secret =
    process.env.CHAT_ACTOR_TOKEN_SECRET ?? process.env.NEXTAUTH_SECRET ?? process.env.JWT_SECRET;
  if (!secret) {
    throw new Error("Missing CHAT_ACTOR_TOKEN_SECRET (or NEXTAUTH_SECRET/JWT_SECRET)");
  }
  return createHmac("sha256", secret).update(payloadEncoded).digest("base64url");
}

function isValidPayload(value: ActorTokenPayload): value is ActorTokenPayload {
  if (typeof value.actor_id !== "string" || value.actor_id.trim().length === 0) return false;
  if (value.actor_role !== "admin" && value.actor_role !== "operator") return false;
  if (typeof value.exp !== "number" || !Number.isFinite(value.exp)) return false;
  return true;
}
