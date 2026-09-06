export type BatchUploadStatus = "pending" | "uploading" | "success" | "failed";

export type BatchUploadFileState<T = File> = {
  file: T;
  status: BatchUploadStatus;
  referenceId?: string;
  folderId?: string | null;
  errorCode?: string;
};

export type UploadPolicy = { maxBytes: number; allowedExtensions: string[]; mimeTypes: Record<string, string[]> };
export const DEFAULT_UPLOAD_POLICY: UploadPolicy = {
  maxBytes: 50 * 1024 * 1024,
  allowedExtensions: [
    ".pdf", ".txt", ".md", ".doc", ".docx", ".ppt", ".pptx", ".png", ".jpg", ".jpeg", ".webp", ".gif",
    ".mp4", ".mov", ".avi", ".mkv", ".webm",
  ],
  mimeTypes: {},
};
export const REFERENCE_MAX_SIZE_BYTES = DEFAULT_UPLOAD_POLICY.maxBytes;
export const REFERENCE_ALLOWED_EXTENSIONS = new Set([
  ".pdf", ".txt", ".md", ".doc", ".docx", ".ppt", ".pptx", ".png", ".jpg", ".jpeg", ".webp", ".gif",
  ".mp4", ".mov", ".avi", ".mkv", ".webm",
]);
const REFERENCE_EXTENSION_MIME_TYPES: Record<string, Set<string>> = {
  ".pdf": new Set(["application/pdf"]), ".txt": new Set(["text/plain"]), ".md": new Set(["text/markdown", "text/plain"]),
  ".doc": new Set(["application/msword", "application/octet-stream"]), ".docx": new Set(["application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/octet-stream"]),
  ".ppt": new Set(["application/vnd.ms-powerpoint", "application/octet-stream"]), ".pptx": new Set(["application/vnd.openxmlformats-officedocument.presentationml.presentation", "application/octet-stream"]),
  ".png": new Set(["image/png"]), ".jpg": new Set(["image/jpeg"]), ".jpeg": new Set(["image/jpeg"]), ".webp": new Set(["image/webp"]), ".gif": new Set(["image/gif"]),
  ".mp4": new Set(["video/mp4"]), ".mov": new Set(["video/quicktime"]), ".avi": new Set(["video/x-msvideo"]), ".mkv": new Set(["video/x-matroska"]), ".webm": new Set(["video/webm"]),
};

export function preflightCampaignReferenceFiles(files: File[], policy: UploadPolicy | number = DEFAULT_UPLOAD_POLICY): BatchUploadFileState<File>[] {
  const configuredPolicy = typeof policy === "number" ? { ...DEFAULT_UPLOAD_POLICY, maxBytes: policy } : { ...DEFAULT_UPLOAD_POLICY, ...policy };
  return files.map((file) => {
    const extension = `.${file.name.split(".").pop()?.toLowerCase() ?? ""}`;
    const mimeTypes = configuredPolicy.mimeTypes[extension] ?? [...(REFERENCE_EXTENSION_MIME_TYPES[extension] ?? [])];
    const errorCode = file.size > configuredPolicy.maxBytes ? "FILE_TOO_LARGE" : !configuredPolicy.allowedExtensions.includes(extension)
      ? "UNSUPPORTED_FILE_TYPE" : file.type && !mimeTypes.includes(file.type)
        ? "UNSUPPORTED_FILE_TYPE" : undefined;
    return { file, status: errorCode ? "failed" : "pending", errorCode };
  });
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
