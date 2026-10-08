export type ReferenceAudit = { generationContextId?: string; brandContext?: Record<string, unknown>; projectDescription?: string; immutableReferenceIds?: string[]; adjustableReferenceIds?: string[]; partitions?: { immutable: ReferenceAuditPartition[]; adjustable: ReferenceAuditPartition[] }; candidateCount?: number; totalLimit?: number; mandatorySelectedCount?: number; mandatoryAttachedCount?: number; userSelectedCount?: number; userAttachedCount?: number; ragSelectedCount?: number; ragAttachedCount?: number; selectedCount: number; attachedCount: number; multimodal: boolean; failures: ReferenceAuditFailure[]; references: ReferenceAuditReference[] };
export type ReferenceAuditReference = { referenceId: string; fileName: string; mimeType: string; folder: string; sha256: string; provenance?: "immutable" | "adjustable"; selected?: boolean; packId?: string; packName?: string; packRole?: string; selectionMode?: string; selectionReason?: string; priority?: number; sourceType?: string };
export type ReferenceAuditPartition = Pick<ReferenceAuditReference, "referenceId" | "provenance" | "selected">;
export type ReferenceAuditFailure = { referenceId: string; category: string; provenance?: "immutable" | "adjustable"; packId?: string; packName?: string; packRole?: string; selectionMode?: string; selectionReason?: string; priority?: number; sourceType?: string };

function isRecord(value: unknown): value is Record<string, unknown> { return value !== null && typeof value === "object" && !Array.isArray(value); }
function displayString(value: unknown, fallback: string) { return typeof value === "string" || typeof value === "number" || typeof value === "boolean" ? String(value) : fallback; }
function displayOptionalString(value: unknown) { return typeof value === "string" || typeof value === "number" || typeof value === "boolean" ? String(value) : undefined; }
function unsafeString(value: string, key = "") { const normalized = value.trim().toLowerCase(); const pathKey = new Set(["reference_id", "reference_pack_id", "pack_name", "pack_role", "file_name", "folder", "provenance"]); return !normalized || normalized.startsWith("data:") || normalized.startsWith("file://") || (pathKey.has(key) && /[\\/]/.test(value)) || (key !== "sha256" && key !== "mime_type" && /^[a-z0-9+/]{16,}={0,2}$/i.test(value)); }
function safeDisplayString(value: unknown, fallback: string, key: string) { const result = displayOptionalString(value); return result && !unsafeString(result, key) ? result : fallback; }
function safeOptionalString(value: unknown, key: string) { const result = displayOptionalString(value); return result && !unsafeString(result, key) ? result : undefined; }
function validCount(value: unknown): value is number { return typeof value === "number" && Number.isInteger(value) && value >= 0; }
function displayOptionalNumber(value: unknown) { return typeof value === "number" && Number.isFinite(value) ? value : undefined; }
function displayIds(value: unknown) { return Array.isArray(value) ? value.filter(item => typeof item === "string" || typeof item === "number").map(String) : undefined; }
function partition(value: unknown): ReferenceAuditPartition[] { return Array.isArray(value) ? value.filter(isRecord).map(item => ({ referenceId: safeDisplayString(item.reference_id, "Unknown reference", "reference_id"), ...(item.provenance === "immutable" || item.provenance === "adjustable" ? { provenance: item.provenance } : {}), ...(typeof item.selected === "boolean" ? { selected: item.selected } : {}) })) : []; }
function provenance(value: Record<string, unknown>) {
  const packId = safeOptionalString(value.reference_pack_id, "reference_pack_id");
  const packName = safeOptionalString(value.pack_name, "pack_name");
  const packRole = safeOptionalString(value.pack_role, "pack_role");
  const selectionMode = safeOptionalString(value.selection_mode, "selection_mode");
  const selectionReason = safeOptionalString(value.selection_reason, "selection_reason");
  const priority = displayOptionalNumber(value.priority);
  const sourceType = safeOptionalString(value.source_type, "source_type");
  return { ...(packId ? { packId } : {}), ...(packName ? { packName } : {}), ...(packRole ? { packRole } : {}), ...(selectionMode ? { selectionMode } : {}), ...(selectionReason ? { selectionReason } : {}), ...(priority !== undefined ? { priority } : {}), ...(sourceType ? { sourceType } : {}) };
}

export function removeBinaryData(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(removeBinaryData);
  if (!isRecord(value)) return value;
  const binaryKeys = new Set(["data", "image_data", "base64", "stored_path", "binary_data", "bytes"]);
  return Object.fromEntries(Object.entries(value).filter(([key, entry]) => !binaryKeys.has(key.toLowerCase()) && !(typeof entry === "string" && unsafeString(entry, key))).map(([key, entry]) => [key, removeBinaryData(entry)]));
}

export function normalizeReferenceAudit(value: unknown): ReferenceAudit | null {
  if (!isRecord(value) || !validCount(value.selected_count) || !validCount(value.attached_count) || !Array.isArray(value.failures) || !Array.isArray(value.references)) return null;
  const partitions = isRecord(value.partitions) ? { immutable: partition(value.partitions.immutable), adjustable: partition(value.partitions.adjustable) } : undefined;
  return {
    ...(safeOptionalString(value.generation_context_id, "generation_context_id") ? { generationContextId: safeOptionalString(value.generation_context_id, "generation_context_id") } : {}),
    ...(isRecord(value.brand_context) ? { brandContext: removeBinaryData(value.brand_context) as Record<string, unknown> } : {}),
    ...(safeOptionalString(value.project_description, "project_description") ? { projectDescription: safeOptionalString(value.project_description, "project_description") } : {}),
    ...(displayIds(value.immutable_reference_ids) ? { immutableReferenceIds: displayIds(value.immutable_reference_ids) } : {}),
    ...(displayIds(value.adjustable_reference_ids) ? { adjustableReferenceIds: displayIds(value.adjustable_reference_ids) } : {}),
    ...(partitions ? { partitions } : {}),
    ...(validCount(value.candidate_count) ? { candidateCount: value.candidate_count } : {}),
    ...(validCount(value.total_limit) ? { totalLimit: value.total_limit } : {}),
    ...(validCount(value.mandatory_selected_count) ? { mandatorySelectedCount: value.mandatory_selected_count } : {}),
    ...(validCount(value.mandatory_attached_count) ? { mandatoryAttachedCount: value.mandatory_attached_count } : {}),
    ...(validCount(value.user_selected_count) ? { userSelectedCount: value.user_selected_count } : {}),
    ...(validCount(value.user_attached_count) ? { userAttachedCount: value.user_attached_count } : {}),
    ...(validCount(value.rag_selected_count) ? { ragSelectedCount: value.rag_selected_count } : {}),
    ...(validCount(value.rag_attached_count) ? { ragAttachedCount: value.rag_attached_count } : {}),
    selectedCount: value.selected_count,
    attachedCount: value.attached_count,
    multimodal: value.multimodal === true,
    failures: value.failures.filter(isRecord).map(failure => ({ referenceId: safeDisplayString(failure.reference_id, "Unknown reference", "reference_id"), category: safeDisplayString(failure.category, "Unknown failure", "category"), ...(failure.provenance === "immutable" || failure.provenance === "adjustable" ? { provenance: failure.provenance } : {}), ...provenance(failure) })),
    references: value.references.filter(isRecord).map(reference => ({ referenceId: safeDisplayString(reference.reference_id, "Unknown reference", "reference_id"), fileName: safeDisplayString(reference.file_name, "File name not recorded", "file_name"), mimeType: safeDisplayString(reference.mime_type, "MIME type not recorded", "mime_type"), folder: safeDisplayString(reference.folder, "Folder not recorded", "folder"), sha256: safeDisplayString(reference.sha256, "SHA-256 not recorded", "sha256"), ...(reference.provenance === "immutable" || reference.provenance === "adjustable" ? { provenance: reference.provenance } : {}), ...(typeof reference.selected === "boolean" ? { selected: reference.selected } : {}), ...provenance(reference) })),
  };
}

export function referenceAuditFromPayloads(payloads: Array<{ context_json?: unknown }>): ReferenceAudit | null {
  return payloads.map(payload => isRecord(payload.context_json) ? normalizeReferenceAudit(payload.context_json.reference_audit) : null).find((audit): audit is ReferenceAudit => audit !== null) ?? null;
}
