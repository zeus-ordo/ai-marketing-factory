import { NextResponse } from "next/server.js";
import { getPool } from "../../../lib/db.ts";
import { buildCampaignQuery } from "../../../lib/query.ts";
import { hasValidSession } from "../../../lib/session.ts";

export async function GET(request: Request) {
  if (!hasValidSession(request)) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  try { const query = buildCampaignQuery(new URL(request.url).searchParams.get("search") ?? ""); return NextResponse.json((await getPool().query(query.text, query.values)).rows.map(row => ({ campaign_id: row.campaign_id, campaign_name: row.campaign_name || row.campaign_id, status: row.status, created_at: row.created_at }))); } catch { return NextResponse.json({ error: "Unable to load campaigns" }, { status: 500 }); }
}
