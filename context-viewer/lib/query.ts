export type Query = { text: string; values: unknown[] };
export type Filters = { campaignId?: string; generationContextId?: string; runId?: string; activityType?: string; status?: string; from?: string; to?: string; limit?: number; offset?: number };

function isSecretKey(key: string): boolean {
  const normalized = key.replace(/[^a-z0-9]/gi, "").toLowerCase();
  if (normalized.endsWith("tokencount")) return false;
  return ["apikey", "token", "password", "secret", "authorization", "credential"].some(marker => normalized.includes(marker));
}

function redactString(value: string): string {
  return value
    .replace(/\bBearer\s+[A-Za-z0-9._~+/=-]+/gi, "Bearer [REDACTED]")
    .replace(/([?&](?:api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|password|secret|token|authorization|credential)[^=]*=)[^&#\s]+/gi, "$1[REDACTED]")
    .replace(/(\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|password|secret|token|credential)[^\s:=]*\s*[:=]\s*["']?)[^&"',}\s]+/gi, "$1[REDACTED]")
    .replace(/(\b[a-z][a-z0-9+.-]*:\/\/[^/\s:@]+:)[^@/\s]+(@)/gi, "$1[REDACTED]$2");
}

export function redactSecrets(value: unknown): any {
  if (Array.isArray(value)) return value.map(redactSecrets);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, isSecretKey(key) ? "[REDACTED]" : redactSecrets(item)]));
  }
  return typeof value === "string" ? redactString(value) : value;
}

export function buildContextListQuery(filters: Filters = {}): Query {
  const values: unknown[] = [];
  const clauses: string[] = [];
  for (const [column, value] of [["c.campaign_id", filters.campaignId], ["gc.generation_context_id", filters.generationContextId], ["gc.run_id", filters.runId]] as const) {
    if (value?.trim()) { values.push(value); clauses.push(`${column} = $${values.length}`); }
  }
  if (filters.activityType?.trim()) {
    values.push(filters.activityType);
    clauses.push(`(ct.task_type = $${values.length} OR EXISTS (SELECT 1 FROM llm_generation_payloads lp_filter WHERE lp_filter.generation_context_id = gc.generation_context_id AND lp_filter.task_type = $${values.length}))`);
  }
  if (filters.status?.trim()) { values.push(filters.status); clauses.push(`COALESCE(ct.status, c.status) = $${values.length}`); }
  if (filters.from?.trim()) { values.push(filters.from); clauses.push(`gc.created_at >= $${values.length}::date`); }
  if (filters.to?.trim()) { values.push(filters.to); clauses.push(`gc.created_at < ($${values.length}::date + INTERVAL '1 day')`); }
  const limit = Math.min(Math.max(Number(filters.limit) || 50, 1), 100);
  const rawOffset = Number(filters.offset);
  const offset = Number.isFinite(rawOffset) ? Math.min(Math.max(rawOffset, 0), 100_000) : 0;
  values.push(limit, offset);
  return {
    text: `SELECT c.campaign_id, COALESCE(NULLIF(c.brief_json->>'campaign_name', ''), c.campaign_id) AS campaign_name, COALESCE(ct.status, c.status) AS status, gc.generation_context_id, gc.run_id, gc.created_at, COALESCE(ct.task_type, MIN(lp.task_type)) AS activity_type, COUNT(DISTINCT gci.generation_context_item_id)::int AS context_item_count, COUNT(DISTINCT lp.payload_id)::int AS payload_count, (SELECT COUNT(*)::int FROM asset_outputs ao WHERE ao.campaign_id = gc.campaign_id AND (ao.run_id = gc.run_id OR (ao.run_id IS NULL AND ao.task_id = gc.task_id))) AS output_count
      FROM campaigns c JOIN generation_contexts gc ON gc.campaign_id = c.campaign_id
      LEFT JOIN campaign_tasks ct ON ct.task_id = gc.task_id AND ct.campaign_id = gc.campaign_id
      LEFT JOIN generation_context_items gci ON gci.generation_context_id = gc.generation_context_id
      LEFT JOIN llm_generation_payloads lp ON lp.campaign_id = gc.campaign_id AND lp.run_id = gc.run_id AND lp.generation_context_id = gc.generation_context_id
      ${clauses.length ? `WHERE ${clauses.join(" AND ")}` : ""} GROUP BY c.campaign_id, c.brief_json, c.status, ct.status, ct.task_type, gc.generation_context_id, gc.run_id, gc.created_at ORDER BY gc.created_at DESC LIMIT $${values.length - 1} OFFSET $${values.length}`,
    values,
  };
}

export function buildCampaignQuery(search = ""): Query {
  return { text: "SELECT campaign_id, COALESCE(NULLIF(brief_json->>'campaign_name', ''), campaign_id) AS campaign_name, status, created_at FROM campaigns WHERE deleted_at IS NULL AND (campaign_id ILIKE $1 OR brief_json->>'campaign_name' ILIKE $1) ORDER BY created_at DESC LIMIT 100", values: [`%${search}%`] };
}

export function buildContextDetailQuery(id: string): Query {
  return { text: `SELECT gc.generation_context_id, gc.campaign_id, gc.run_id, gc.created_at, gc.internal_token_count, gc.external_token_count, gc.internal_ratio, gc.external_ratio, gc.external_source_urls_json, gc.external_search_status, gc.external_search_error, gc.task_id, gc.selected_reference_ids_json, gc.matched_folder_names_json,
      COALESCE((SELECT jsonb_agg(gci ORDER BY gci.position) FROM generation_context_items gci WHERE gci.generation_context_id = gc.generation_context_id), '[]'::jsonb) AS items,
      COALESCE((SELECT jsonb_agg(jsonb_build_object('payload_id', lp.payload_id, 'task_id', lp.task_id, 'task_type', lp.task_type, 'provider', lp.provider, 'model', lp.model, 'prompt', lp.prompt, 'context_json', lp.context_json, 'created_at', lp.created_at) ORDER BY lp.created_at) FROM llm_generation_payloads lp WHERE lp.campaign_id = gc.campaign_id AND lp.run_id = gc.run_id AND lp.generation_context_id = gc.generation_context_id), '[]'::jsonb) AS payloads,
      COALESCE((SELECT jsonb_agg(jsonb_build_object('asset_id', ao.asset_id, 'task_id', ao.task_id, 'asset_type', ao.asset_type, 'url', ao.url, 'metadata_json', ao.metadata_json, 'validation_status', ao.validation_status, 'created_at', ao.created_at) ORDER BY ao.created_at) FROM asset_outputs ao WHERE ao.campaign_id = gc.campaign_id AND (ao.run_id = gc.run_id OR (ao.run_id IS NULL AND ao.task_id = gc.task_id))), '[]'::jsonb) AS outputs
      FROM generation_contexts gc WHERE gc.generation_context_id = $1 LIMIT 1`, values: [id] };
}
