import { createHmac, timingSafeEqual } from "node:crypto";
import type { ChatContext } from "@/lib/types/chatbot";

type PendingAction = NonNullable<ChatContext["pendingAction"]>;

type SignedPayload = PendingAction & {
  exp: number;
};

const DEFAULT_TTL_MS = 5 * 60 * 1000;

export function createPendingActionToken(action: PendingAction): string {
  const ttlMs = Number(process.env.CHAT_PENDING_ACTION_TTL_MS ?? DEFAULT_TTL_MS);
  const payload: SignedPayload = {
    ...action,
    exp: Date.now() + (Number.isFinite(ttlMs) && ttlMs > 0 ? ttlMs : DEFAULT_TTL_MS),
  };

  const payloadEncoded = Buffer.from(JSON.stringify(payload), "utf-8").toString("base64url");
  const signature = sign(payloadEncoded);
  return `${payloadEncoded}.${signature}`;
}

export function verifyPendingActionToken(token: string): PendingAction | null {
  const [payloadEncoded, signature] = token.split(".");
  if (!payloadEncoded || !signature) return null;

  const expectedSignature = sign(payloadEncoded);
  const actual = Buffer.from(signature);
  const expected = Buffer.from(expectedSignature);
  if (actual.length !== expected.length) return null;
  if (!timingSafeEqual(actual, expected)) return null;

  try {
    const parsed = JSON.parse(Buffer.from(payloadEncoded, "base64url").toString("utf-8")) as SignedPayload;
    if (!isValidPayload(parsed)) return null;
    if (Date.now() > parsed.exp) return null;

    return {
      type: parsed.type,
      nonce: parsed.nonce,
      campaignId: parsed.campaignId,
      referenceId: parsed.referenceId,
      reviewId: parsed.reviewId,
      draftBrief: parsed.draftBrief,
      createdAt: parsed.createdAt,
    };
  } catch {
    return null;
  }
}

function sign(payloadEncoded: string): string {
  const secret =
    process.env.CHAT_PENDING_ACTION_SECRET ?? process.env.NEXTAUTH_SECRET ?? process.env.JWT_SECRET;
  if (!secret) {
    throw new Error("Missing CHAT_PENDING_ACTION_SECRET (or NEXTAUTH_SECRET/JWT_SECRET)");
  }
  return createHmac("sha256", secret).update(payloadEncoded).digest("base64url");
}

function isValidPayload(value: SignedPayload): value is SignedPayload {
  const validType = value.type === "delete_reference" || value.type === "approve_review" || value.type === "create_campaign" || value.type === "run_campaign";
  if (!validType) return false;
  if (typeof value.createdAt !== "string" || value.createdAt.length === 0) return false;
  if (typeof value.exp !== "number" || !Number.isFinite(value.exp)) return false;
  if (value.nonce != null && (typeof value.nonce !== "string" || value.nonce.length < 4 || value.nonce.length > 12)) {
    return false;
  }
  if (value.campaignId != null && typeof value.campaignId !== "string") return false;
  if (value.referenceId != null && typeof value.referenceId !== "string") return false;
  if (value.reviewId != null && typeof value.reviewId !== "string") return false;
  if (value.draftBrief != null && typeof value.draftBrief !== "object") return false;
  return true;
}
