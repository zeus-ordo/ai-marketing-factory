import { createHmac, timingSafeEqual } from "node:crypto";

export const SESSION_COOKIE = "context_viewer_session";

function signature(value: string, secret: string): string {
  return createHmac("sha256", secret).update(value).digest("base64url");
}

export function signSession(username: string, secret: string): string {
  const value = `${username}.${Date.now()}`;
  return `${Buffer.from(value).toString("base64url")}.${signature(value, secret)}`;
}

export function isValidSession(token: string | undefined, secret: string | undefined): boolean {
  if (!token || !secret) return false;
  const [encoded, supplied] = token.split(".");
  if (!encoded || !supplied) return false;
  try {
    const value = Buffer.from(encoded, "base64url").toString("utf8");
    const expected = signature(value, secret);
    return supplied.length === expected.length && timingSafeEqual(Buffer.from(supplied), Buffer.from(expected));
  } catch {
    return false;
  }
}

export function hasValidSession(request: Request): boolean {
  const secret = process.env.SESSION_SECRET;
  const cookie = request.headers.get("cookie")?.match(new RegExp(`${SESSION_COOKIE}=([^;]+)`))?.[1];
  return isValidSession(cookie, secret);
}
