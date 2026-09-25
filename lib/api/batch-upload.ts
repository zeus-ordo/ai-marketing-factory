export type BatchUploadStatus = "pending" | "uploading" | "success" | "failed";

export type BatchUploadFileState<T = File> = {
  file: T;
  status: BatchUploadStatus;
  referenceId?: string;
  folderId?: string | null;
  errorCode?: string;
};

export type UploadPolicy = { maxBytes: number; allowedExtensions: string[]; mimeTypes: Record<string, string[]> };

const STABLE_UPLOAD_ERROR_CODES = [
  "FILE_TOO_LARGE",
  "UNSUPPORTED_FILE_TYPE",
  "CAMPAIGN_ACCESS_DENIED",
  "UPLOAD_TIMEOUT",
  "PERSISTENCE_ERROR",
] as const;

function stableUploadErrorCode(reason: unknown): string {
  const candidates = [
    reason instanceof Error ? reason.message : "",
    reason && typeof reason === "object" && "detail" in reason ? String(reason.detail) : "",
    reason && typeof reason === "object" && "errorCode" in reason ? String(reason.errorCode) : "",
  ];
  return STABLE_UPLOAD_ERROR_CODES.find((code) => candidates.some((value) => value === code || value.includes(code))) ?? "UPLOAD_FAILED";
}

export function preflightCampaignReferenceFiles(files: File[], policy: UploadPolicy): BatchUploadFileState<File>[] {
  return files.map((file) => {
    const extension = `.${file.name.split(".").pop()?.toLowerCase() ?? ""}`;
    const errorCode = file.size > policy.maxBytes ? "FILE_TOO_LARGE" : !policy.allowedExtensions.includes(extension)
      ? "UNSUPPORTED_FILE_TYPE" : file.type && !(policy.mimeTypes[extension] ?? []).includes(file.type)
        ? "UNSUPPORTED_FILE_TYPE" : undefined;
    return { file, status: errorCode ? "failed" : "pending", errorCode };
  });
}

export function mergeBatchUploadStates<T>(existing: BatchUploadFileState<T>[], updates: BatchUploadFileState<T>[]): BatchUploadFileState<T>[] {
  return existing.map((item) => updates.find((update) => update.file === item.file) ?? item);
}

export function isCampaignStartEnabled<T>(states: BatchUploadFileState<T>[]): boolean {
  return states.length > 0 && states.every((item) => item.status === "success");
}

export function hasBlockingBatchUploadStates<T>(states: BatchUploadFileState<T>[]): boolean {
  return states.some((item) => item.status !== "success");
}

export function canStartAfterUploadRemoval<T, U>(referenceStates: BatchUploadFileState<T>[], knowledgeStates: BatchUploadFileState<U>[]): boolean {
  return !hasBlockingBatchUploadStates(referenceStates) && !hasBlockingBatchUploadStates(knowledgeStates);
}

export async function uploadBatchItems<T>(
  items: BatchUploadFileState<T>[],
  upload: (item: T) => Promise<{ referenceId?: string; folderId?: string | null }>,
  concurrency = 3,
  onStateChange?: (states: BatchUploadFileState<T>[]) => void,
): Promise<BatchUploadFileState<T>[]> {
  const results = items.map((item) => ({ ...item }));
  const pendingIndexes = results.map((item, index) => item.status === "pending" ? index : -1).filter((index) => index >= 0);
  let nextIndex = 0;
  const notify = () => onStateChange?.(results.map((item) => ({ ...item })));
  const worker = async () => {
    while (nextIndex < pendingIndexes.length) {
      const index = pendingIndexes[nextIndex++];
      results[index].status = "uploading";
      notify();
      const settled = await Promise.allSettled([upload(results[index].file)]);
      const result = settled[0];
      if (result.status === "fulfilled") {
        results[index].status = "success";
        results[index].referenceId = result.value.referenceId;
        results[index].folderId = result.value.folderId;
        delete results[index].errorCode;
      } else {
        results[index].status = "failed";
        results[index].errorCode = stableUploadErrorCode(result.reason);
      }
      notify();
    }
  };
  const workers = Array.from({ length: Math.min(Math.max(1, concurrency), pendingIndexes.length) }, () => worker());
  const workerResults = await Promise.allSettled(workers);
  workerResults.forEach((result) => {
    if (result.status === "rejected") notify();
  });
  return results;
}
