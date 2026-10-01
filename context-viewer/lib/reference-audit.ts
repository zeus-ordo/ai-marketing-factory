export type ReferenceAudit = { candidateCount?: number; selectedCount: number; attachedCount: number; multimodal: boolean; failures: ReferenceAuditFailure[]; references: ReferenceAuditReference[] };
export type ReferenceAuditReference = { referenceId: string; fileName: string; mimeType: string; folder: string; sha256: string; packId?: string; packName?: string; packRole?: string; selectionMode?: string; selectionReason?: string; priority?: number; sourceType?: string };
export type ReferenceAuditFailure = { referenceId: string; category: string; packId?: string; packName?: string; packRole?: string; selectionMode?: string; selectionReason?: string; priority?: number; sourceType?: string };

function isRecord(value: unknown): value is Record<string, unknown> { return value !== null && typeof value === "object" && !Array.isArray(value); }
function displayString(value: unknown, fallback: string) { return typeof value === "string" || typeof value === "number" || typeof value === "boolean" ? String(value) : fallback; }
function displayOptionalString(value: unknown) { return typeof value === "string" || typeof value === "number" || typeof value === "boolean" ? String(value) : undefined; }
function validCount(value: unknown): value is number { return typeof value === "number" && Number.isInteger(value) && value >= 0; }
function displayOptionalNumber(value: unknown) { return typeof value === "number" && Number.isFinite(value) ? value : undefined; }
function provenance(value: Record<string, unknown>) {
  const packId = displayOptionalString(value.reference_pack_id);
  const packName = displayOptionalString(value.pack_name);
  const packRole = displayOptionalString(value.pack_role);
  const selectionMode = displayOptionalString(value.selection_mode);
  const selectionReason = displayOptionalString(value.selection_reason);
  const priority = displayOptionalNumber(value.priority);
  const sourceType = displayOptionalString(value.source_type);
  return { ...(packId ? { packId } : {}), ...(packName ? { packName } : {}), ...(packRole ? { packRole } : {}), ...(selectionMode ? { selectionMode } : {}), ...(selectionReason ? { selectionReason } : {}), ...(priority !== undefined ? { priority } : {}), ...(sourceType ? { sourceType } : {}) };
}

export function removeBinaryData(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(removeBinaryData);
  if (!isRecord(value)) return value;
  const binaryKeys = new Set(["data", "image_data", "base64"]);
  return Object.fromEntries(Object.entries(value).filter(([key]) => !binaryKeys.has(key.toLowerCase())).map(([key, entry]) => [key, removeBinaryData(entry)]));
}

export function normalizeReferenceAudit(value: unknown): ReferenceAudit | null {
  if (!isRecord(value) || !validCount(value.selected_count) || !validCount(value.attached_count) || !Array.isArray(value.failures) || !Array.isArray(value.references)) return null;
  return {
    ...(validCount(value.candidate_count) ? { candidateCount: value.candidate_count } : {}),
    selectedCount: value.selected_count,
    attachedCount: value.attached_count,
    multimodal: value.multimodal === true,
    failures: value.failures.filter(isRecord).map(failure => ({ referenceId: displayString(failure.reference_id, "Unknown reference"), category: displayString(failure.category, "Unknown failure"), ...provenance(failure) })),
    references: value.references.filter(isRecord).map(reference => ({ referenceId: displayString(reference.reference_id, "Unknown reference"), fileName: displayString(reference.file_name, "File name not recorded"), mimeType: displayString(reference.mime_type, "MIME type not recorded"), folder: displayString(reference.folder, "Folder not recorded"), sha256: displayString(reference.sha256, "SHA-256 not recorded"), ...provenance(reference) })),
  };
}

export function referenceAuditFromPayloads(payloads: Array<{ context_json?: unknown }>): ReferenceAudit | null {
  return payloads.map(payload => isRecord(payload.context_json) ? normalizeReferenceAudit(payload.context_json.reference_audit) : null).find((audit): audit is ReferenceAudit => audit !== null) ?? null;
}
