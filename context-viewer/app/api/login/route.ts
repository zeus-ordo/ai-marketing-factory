import { timingSafeEqual } from "node:crypto";
import { NextResponse } from "next/server.js";
import { SESSION_COOKIE, signSession } from "../../../lib/session.ts";

function equal(left: string | undefined, right: string | undefined): boolean {
  if (!left || !right) return false;
  const a = Buffer.from(left), b = Buffer.from(right);
  return a.length === b.length && timingSafeEqual(a, b);
}

export async function POST(request: Request) {
  const body = await request.json().catch(() => ({}));
  if (!process.env.SESSION_SECRET || !equal(body.username, process.env.VIEWER_USERNAME) || !equal(body.password, process.env.VIEWER_PASSWORD)) return NextResponse.json({ error: "Invalid credentials" }, { status: 401 });
  const response = NextResponse.json({ ok: true });
  response.cookies.set(SESSION_COOKIE, signSession(body.username, process.env.SESSION_SECRET), { httpOnly: true, sameSite: "strict", secure: process.env.NODE_ENV === "production", path: "/", maxAge: 60 * 60 * 8 });
  return response;
}
