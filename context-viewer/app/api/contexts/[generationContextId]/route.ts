import { NextResponse } from "next/server.js";
import { getPool } from "../../../../lib/db.ts";
import { buildContextDetailQuery, redactSecrets } from "../../../../lib/query.ts";
import { removeBinaryData } from "../../../../lib/reference-audit.ts";
import { hasValidSession } from "../../../../lib/session.ts";

export const contextDetailDeps = { getPool };

export async function GET(request: Request, { params }: { params: Promise<{ generationContextId: string }> }) {
  if (!hasValidSession(request)) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  try { const query = buildContextDetailQuery((await params).generationContextId); const result = await contextDetailDeps.getPool().query(query.text, query.values); if (!result.rows[0]) return NextResponse.json({ error: "Not found" }, { status: 404 }); return NextResponse.json(redactSecrets(removeBinaryData(result.rows[0]))); } catch { return NextResponse.json({ error: "Unable to load context" }, { status: 500 }); }
}
