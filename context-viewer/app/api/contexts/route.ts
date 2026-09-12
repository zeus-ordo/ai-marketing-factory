import { NextResponse } from "next/server";
import { getPool } from "../../../lib/db";
import { buildContextListQuery } from "../../../lib/query";
import { hasValidSession } from "../../../lib/session";

export async function GET(request: Request) {
  if (!hasValidSession(request)) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  const params = new URL(request.url).searchParams;
  try { const query = buildContextListQuery({ campaignId: params.get("campaign_id") ?? undefined, generationContextId: params.get("generation_context_id") ?? undefined, runId: params.get("run_id") ?? undefined, limit: Number(params.get("limit") ?? 50), offset: Number(params.get("offset") ?? 0) }); return NextResponse.json((await getPool().query(query.text, query.values)).rows); } catch { return NextResponse.json({ error: "Unable to load contexts" }, { status: 500 }); }
}
