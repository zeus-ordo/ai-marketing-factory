export type Query = { text: string; values: unknown[] };
export type Filters = { campaignId?: string; generationContextId?: string; runId?: string; limit?: number; offset?: number };

const SECRET_KEY = /^(api[_-]?key|access[_-]?token|client[_-]?secret|credential(?:[_-].*)?|authorization|password|secret|token)$/i;

export function redactSecrets(value: unknown): any {
  if (Array.isArray(value)) return value.map(redactSecrets);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, SECRET_KEY.test(key) ? "[REDACTED]" : redactSecrets(item)]));
  }
  return value;
}

export function buildContextListQuery(filters: Filters = {}): Query {
  const values: unknown[] = [];
  const clauses: string[] = [];
  for (const [column, value] of [["c.campaign_id", filters.campaignId], ["gc.generation_context_id", filters.generationContextId], ["gc.run_id", filters.runId]] as const) {
    if (value) { values.push(value); clauses.push(`${column} = $${values.length}`); }
  }
  const limit = Math.min(Math.max(Number(filters.limit) || 50, 1), 100);
  const offset = Math.max(Number(filters.offset) || 0, 0);
  values.push(limit, offset);
  return {
    text: `SELECT c.campaign_id, gc.generation_context_id, gc.run_id, gc.created_at, COUNT(DISTINCT gci.generation_context_item_id)::int AS context_item_count, COUNT(DISTINCT lp.payload_id)::int AS payload_count
      FROM campaigns c JOIN generation_contexts gc ON gc.campaign_id = c.campaign_id
      LEFT JOIN generation_context_items gci ON gci.generation_context_id = gc.generation_context_id
      LEFT JOIN llm_generation_payloads lp ON lp.campaign_id = gc.campaign_id AND lp.run_id = gc.run_id AND lp.generation_context_id = gc.generation_context_id
      ${clauses.length ? `WHERE ${clauses.join(" AND ")}` : ""} GROUP BY c.campaign_id, gc.generation_context_id, gc.run_id, gc.created_at ORDER BY gc.created_at DESC LIMIT $${values.length - 1} OFFSET $${values.length}`,
    values,
  };
}

export function buildCampaignQuery(search = ""): Query {
  return { text: "SELECT campaign_id, status, created_at FROM campaigns WHERE campaign_id ILIKE $1 ORDER BY created_at DESC LIMIT 100", values: [`%${search}%`] };
}

export function buildContextDetailQuery(id: string): Query {
  return { text: `SELECT gc.generation_context_id, gc.campaign_id, gc.run_id, gc.created_at, gc.internal_token_count, gc.external_token_count,
      COALESCE((SELECT jsonb_agg(gci ORDER BY gci.position) FROM generation_context_items gci WHERE gci.generation_context_id = gc.generation_context_id), '[]'::jsonb) AS items,
      COALESCE((SELECT jsonb_agg(lp ORDER BY lp.created_at) FROM llm_generation_payloads lp WHERE lp.campaign_id = gc.campaign_id AND lp.run_id = gc.run_id AND lp.generation_context_id = gc.generation_context_id), '[]'::jsonb) AS payloads
      FROM generation_contexts gc WHERE gc.generation_context_id = $1 LIMIT 1`, values: [id] };
}
