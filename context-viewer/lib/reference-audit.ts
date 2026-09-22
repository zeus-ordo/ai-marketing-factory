export type ReferenceAudit = { selectedCount: number; attachedCount: number; multimodal: boolean; failures: ReferenceAuditFailure[]; references: ReferenceAuditReference[] };
export type ReferenceAuditReference = { referenceId: string; fileName: string; mimeType: string; folder: string; sha256: string };
export type ReferenceAuditFailure = { referenceId: string; category: string };

function isRecord(value: unknown): value is Record<string, unknown> { return value !== null && typeof value === "object" && !Array.isArray(value); }
function displayString(value: unknown, fallback: string) { return typeof value === "string" || typeof value === "number" || typeof value === "boolean" ? String(value) : fallback; }

export function removeBinaryData(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(removeBinaryData);
  if (!isRecord(value)) return value;
  const binaryKeys = new Set(["data", "image_data", "base64"]);
  return Object.fromEntries(Object.entries(value).filter(([key]) => !binaryKeys.has(key.toLowerCase())).map(([key, entry]) => [key, removeBinaryData(entry)]));
}

export function normalizeReferenceAudit(value: unknown): ReferenceAudit | null {
  if (!isRecord(value) || typeof value.selected_count !== "number" || !Number.isInteger(value.selected_count) || value.selected_count < 0 || typeof value.attached_count !== "number" || !Number.isInteger(value.attached_count) || value.attached_count < 0 || !Array.isArray(value.failures) || !Array.isArray(value.references)) return null;
  return {
    selectedCount: value.selected_count,
    attachedCount: value.attached_count,
    multimodal: value.multimodal === true,
    failures: value.failures.filter(isRecord).map(failure => ({ referenceId: displayString(failure.reference_id, "Unknown reference"), category: displayString(failure.category, "Unknown failure") })),
    references: value.references.filter(isRecord).map(reference => ({ referenceId: displayString(reference.reference_id, "Unknown reference"), fileName: displayString(reference.file_name, "File name not recorded"), mimeType: displayString(reference.mime_type, "MIME type not recorded"), folder: displayString(reference.folder, "Folder not recorded"), sha256: displayString(reference.sha256, "SHA-256 not recorded") })),
  };
}

export function referenceAuditFromPayloads(payloads: Array<{ context_json?: unknown }>): ReferenceAudit | null {
  return payloads.map(payload => isRecord(payload.context_json) ? normalizeReferenceAudit(payload.context_json.reference_audit) : null).find((audit): audit is ReferenceAudit => audit !== null) ?? null;
}
