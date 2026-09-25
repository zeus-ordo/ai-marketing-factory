import { NextResponse } from "next/server.js";
import { SESSION_COOKIE } from "../../../lib/session.ts";

export function POST() { const response = NextResponse.json({ ok: true }); response.cookies.set(SESSION_COOKIE, "", { httpOnly: true, sameSite: "strict", expires: new Date(0), path: "/" }); return response; }
