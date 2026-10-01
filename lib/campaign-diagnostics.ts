import type { CampaignTask, GenerationSourceProvenance } from "./api/campaigns";

export const MAX_TASK_ATTEMPTS = 3;

export function safeExternalUrl(value: string | null | undefined): string | null {
  if (!value) return null;
  try {
    const parsed = new URL(value);
    if (parsed.username || parsed.password) return null;
    return parsed.protocol === "http:" || parsed.protocol === "https:" ? parsed.toString() : null;
  } catch {
    return null;
  }
}

export function sanitizeDiagnosticText(value: string | null | undefined): string {
  return (value || "")
    .replace(/((?:api[_-]?key|token|password|secret)\s*[=:]\s*)[^\s&,]+/gi, "$1[REDACTED]")
    .slice(0, 2000);
}

export function canRetryTask(task: CampaignTask): boolean {
  return task.retryable === true && (task.retry_count || 0) < MAX_TASK_ATTEMPTS;
}

export function provenanceText(source: GenerationSourceProvenance): string {
  return [source.source_type, source.label, source.folder].filter(Boolean).join(" · ");
}
