import { NextResponse } from "next/server";
import { getPool } from "../../../../lib/db";
import { buildContextDetailQuery, redactSecrets } from "../../../../lib/query";
import { hasValidSession } from "../../../../lib/session";

export async function GET(request: Request, { params }: { params: Promise<{ generationContextId: string }> }) {
  if (!hasValidSession(request)) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  try { const query = buildContextDetailQuery((await params).generationContextId); const result = await getPool().query(query.text, query.values); if (!result.rows[0]) return NextResponse.json({ error: "Not found" }, { status: 404 }); return NextResponse.json(redactSecrets(result.rows[0])); } catch { return NextResponse.json({ error: "Unable to load context" }, { status: 500 }); }
}
