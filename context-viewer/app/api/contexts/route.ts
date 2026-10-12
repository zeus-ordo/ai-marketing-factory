import { NextResponse } from "next/server.js";
import { getPool } from "../../../lib/db.ts";
import { buildContextListQuery } from "../../../lib/query.ts";
import { hasValidSession } from "../../../lib/session.ts";

export async function GET(request: Request) {
  if (!hasValidSession(request)) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  const params = new URL(request.url).searchParams;
  const value = (name: string) => params.get(name)?.trim() || undefined;
  try {
    const query = buildContextListQuery({ campaignId: value("campaign_id"), campaignName: value("campaign_name"), generationContextId: value("generation_context_id"), runId: value("run_id"), activityType: value("activity_type"), status: value("status"), from: value("from"), to: value("to"), limit: Number(params.get("limit") ?? 50), offset: Number(params.get("offset") ?? 0) });
    const rows = (await getPool().query(query.text, query.values)).rows;
    return NextResponse.json(rows.map((row) => ({ campaign_id: row.campaign_id, campaign_name: row.campaign_name || row.campaign_id, generation_context_id: row.generation_context_id, run_id: row.run_id, created_at: row.created_at, activity_type: row.activity_type, status: row.status, context_item_count: row.context_item_count, payload_count: row.payload_count, output_count: row.output_count })));
  } catch { return NextResponse.json({ error: "Unable to load contexts" }, { status: 500 }); }
}
