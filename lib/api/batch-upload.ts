export type BatchUploadStatus = "pending" | "uploading" | "success" | "failed";

export type BatchUploadFileState<T = File> = {
  file: T;
  status: BatchUploadStatus;
  referenceId?: string;
  folderId?: string | null;
  errorCode?: string;
};

export type UploadPolicy = { maxBytes: number; allowedExtensions: string[]; mimeTypes: Record<string, string[]> };

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
        results[index].errorCode = result.reason instanceof Error && result.reason.message.startsWith("FILE_") ? result.reason.message : "UPLOAD_FAILED";
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
