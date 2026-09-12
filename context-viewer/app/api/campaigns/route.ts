import { NextResponse } from "next/server";
import { getPool } from "../../../lib/db";
import { buildCampaignQuery } from "../../../lib/query";
import { hasValidSession } from "../../../lib/session";

export async function GET(request: Request) {
  if (!hasValidSession(request)) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  try { const query = buildCampaignQuery(new URL(request.url).searchParams.get("search") ?? ""); return NextResponse.json((await getPool().query(query.text, query.values)).rows); } catch { return NextResponse.json({ error: "Unable to load campaigns" }, { status: 500 }); }
}
