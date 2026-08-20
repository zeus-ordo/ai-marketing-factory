/* eslint-disable react-hooks/set-state-in-effect -- intentional state updates for modal open/close pattern */
"use client";

import { useEffect, useState } from "react";
import { listAssetVersions, regenerateAsset, type AssetVersion } from "@/lib/api/campaigns";
import { useI18n } from "@/lib/i18n/context";

type Props = {
  assetId: string | null;
  open: boolean;
  onClose: () => void;
  showRegenerate?: boolean;
};

export function ReviewAssetPreviewModal({ assetId, open, onClose, showRegenerate = true }: Props) {
  const { t } = useI18n();
  const [versions, setVersions] = useState<AssetVersion[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [regenerating, setRegenerating] = useState(false);
  const [regenerateMsg, setRegenerateMsg] = useState<string | null>(null);

  // Reset state when modal closes
  useEffect(() => {
    if (!open) {
      setVersions([]);
      setLoading(false);
      setError(null);
      setRegenerating(false);
      setRegenerateMsg(null);
    }
  }, [open]);

  // Fetch asset versions when modal opens
  useEffect(() => {
    if (!open || !assetId) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setVersions([]);

    listAssetVersions(assetId)
      .then((data) => {
        if (cancelled) return;
        setVersions(data);
        setLoading(false);
      })
      .catch(() => {
        if (cancelled) return;
        setError(t("review.previewLoadFailed"));
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [open, assetId, t]);

  async function handleRegenerate() {
    if (!assetId) return;
    if (!window.confirm(t("review.confirmRegenerate"))) return;
    setRegenerating(true);
    setRegenerateMsg(null);
    try {
      await regenerateAsset(assetId);
      setRegenerateMsg(t("review.regenerateSubmitted"));
      // Refresh versions after a short delay to allow worker to process
      setTimeout(() => {
        setRegenerating(false);
        void listAssetVersions(assetId).then((data) => {
          setVersions(data);
        });
      }, 3000);
    } catch {
      setRegenerateMsg(t("review.regenerateFailed"));
      setRegenerating(false);
    }
  }

  if (!open) return null;

  const latest = versions[0];
  const latestText = latest ? getAssetText(latest) : "";

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="relative w-full max-w-2xl rounded-2xl border border-slate-200 bg-white shadow-2xl dark:border-slate-700 dark:bg-slate-900">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4 dark:border-slate-700">
          <div>
            <h2 className="text-lg font-semibold">{t("review.previewTitle")}</h2>
            <p className="mt-0.5 font-mono text-xs text-slate-500">{assetId}</p>
          </div>
          <div className="flex items-center gap-2">
            {showRegenerate ? (
              <button
                onClick={handleRegenerate}
                disabled={regenerating || !assetId}
                className="rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-medium text-white disabled:opacity-50 hover:bg-blue-700"
              >
                {regenerating ? t("review.regenerating") : t("review.regenerate")}
              </button>
            ) : null}
            <button
              onClick={onClose}
              className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-800 dark:hover:text-slate-200"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M18 6 6 18" /><path d="m6 6 12 12" />
              </svg>
            </button>
          </div>
        </div>

        {/* Status message */}
        {regenerateMsg && (
          <div className={`mx-6 mt-4 rounded-lg px-3 py-2 text-sm ${regenerateMsg === t("review.regenerateSubmitted") ? "bg-blue-50 text-blue-700" : "bg-red-50 text-red-600"}`}>
            {regenerateMsg}
          </div>
        )}

        {/* Body */}
        <div className="p-6">
          {loading && (
            <div className="flex h-48 items-center justify-center text-sm text-slate-500">
              {t("review.loading")}
            </div>
          )}
          {error && (
            <div className="flex h-48 items-center justify-center text-sm text-red-500">
              {error}
            </div>
          )}
          {!loading && !error && versions.length === 0 && (
            <div className="flex h-48 items-center justify-center text-sm text-slate-500">
              {t("review.noVersions")}
            </div>
          )}
          {!loading && !error && latest && (
            <div className="space-y-4">
              {assetVersionName(latest) ? (
                <div>
                  <p className="text-sm font-semibold text-slate-800 dark:text-slate-100">{assetVersionName(latest)}</p>
                  <p className="font-mono text-xs text-slate-400">{latest.asset_id}</p>
                </div>
              ) : null}
              {/* Version badge */}
              <div className="flex items-center gap-2 text-xs text-slate-500">
                <span className="rounded-full bg-slate-100 px-2 py-0.5 dark:bg-slate-800">
                  {t("review.versionLabel", { version: latest.version_number })}
                </span>
                <span>{new Date(latest.created_at).toLocaleString()}</span>
              </div>

              {/* Asset preview */}
              <div className="flex items-center justify-center rounded-xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-700 dark:bg-slate-950">
                {isVideoVersion(latest) ? (
                  <video
                    src={latest.url}
                    controls
                    preload="metadata"
                    className="max-h-96 w-full rounded-lg"
                  />
                ) : isImageVersion(latest) ? (
                  <div className="relative h-96 w-full">
                    {/* Use a plain img tag so proxied/internal and provider URLs do not require Next image domain config. */}
                    <img
                      src={latest.url}
                      alt={assetId ?? ""}
                      className="h-full w-full object-contain"
                      onError={(e) => {
                        const target = e.target as HTMLImageElement;
                        target.style.display = "none";
                        target.parentElement?.classList.add("after:content-['Image_preview_unavailable']", "after:text-sm", "after:text-slate-500");
                      }}
                    />
                  </div>
                ) : (
                  <pre className="max-h-96 w-full overflow-auto whitespace-pre-wrap text-sm text-slate-700 dark:text-slate-300">
                    {latestText || t("review.noContent")}
                  </pre>
                )}
              </div>

              {/* Download button */}
              {(isImageVersion(latest) || isVideoVersion(latest)) && (
                <button
                  onClick={() => downloadAsset(latest.url, assetId ?? "asset")}
                  className="mt-2 w-full rounded-lg bg-green-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-green-700"
                >
                  {t("review.downloadAsset") ?? "下載"}
                </button>
              )}

              {/* All versions list */}
              {versions.length > 1 && (
                <div>
                  <p className="mb-2 text-xs font-medium text-slate-500">{t("review.allVersions")}</p>
                  <div className="space-y-1">
                    {versions.map((v) => (
                      <div key={v.version_id} className="flex items-center gap-2 text-xs text-slate-600 dark:text-slate-400">
                        <span className="font-mono">{assetVersionName(v) || t("review.versionLabel", { version: v.version_number })}</span>
                        <span className="ml-auto shrink-0 text-slate-400">{new Date(v.created_at).toLocaleString()}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function isImageVersion(version: AssetVersion): boolean {
  const assetType = String(version.metadata_json?.asset_type ?? version.metadata_json?.type ?? "").toLowerCase();
  return assetType === "image" || isImageUrl(version.url);
}

function isVideoVersion(version: AssetVersion): boolean {
  const assetType = String(version.metadata_json?.asset_type ?? version.metadata_json?.type ?? "").toLowerCase();
  return assetType === "video" || isVideoUrl(version.url);
}

function isImageUrl(url: string): boolean {
  return url.startsWith("data:image/")
    || /\.(jpg|jpeg|png|gif|webp|svg)(\?|$|#)/i.test(url)
    || url.includes("/images/")
    || url.includes("/image/");
}

function isVideoUrl(url: string): boolean {
  return /\.(mp4|webm|ogg|mov)(\?|$|#)/i.test(url) || url.includes("/video/") || url.includes("/videos/");
}

function assetVersionName(version: AssetVersion): string {
  const metadata = version.metadata_json ?? {};
  for (const key of ["asset_name", "display_name", "asset_display_name"]) {
    const value = metadata[key];
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return "";
}

function getAssetText(version: AssetVersion): string {
  const metadata = version.metadata_json ?? {};
  const direct = metadata.text ?? metadata.copy ?? metadata.content ?? metadata.manual_text;
  if (typeof direct === "string" && direct.trim()) return direct.trim();

  const adsPlan = metadata.ads_plan ?? metadata.adsStrategy ?? metadata.ads_strategy ?? metadata.strategy;
  if (adsPlan) return formatMetadataValue(adsPlan);

  const variant = metadata.variant;
  if (variant && typeof variant === "object") {
    const body = (variant as Record<string, unknown>).body;
    if (typeof body === "string" && body.trim()) return body.trim();
  }

  return "";
}

function formatMetadataValue(value: unknown, depth = 0): string {
  if (typeof value === "string") return value.trim();
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (value == null) return "";
  const indent = "  ".repeat(depth);
  const childIndent = "  ".repeat(depth + 1);
  if (Array.isArray(value)) {
    return value
      .map((item) => {
        const formatted = formatMetadataValue(item, depth + 1);
        return formatted.includes("\n") ? `${indent}-\n${formatted}` : `${indent}- ${formatted}`;
      })
      .filter(Boolean)
      .join("\n");
  }
  if (typeof value === "object") {
    return Object.entries(value as Record<string, unknown>)
      .map(([key, item]) => {
        const formatted = formatMetadataValue(item, depth + 1);
        if (!formatted) return "";
        return formatted.includes("\n") ? `${indent}${humanizeKey(key)}:\n${formatted}` : `${childIndent}${humanizeKey(key)}: ${formatted}`;
      })
      .filter(Boolean)
      .join("\n");
  }
  return "";
}

function humanizeKey(key: string): string {
  return key.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function downloadAsset(url: string, assetId: string) {
  if (url.startsWith("data:")) {
    const [header, data] = url.split(",");
    const mimeMatch = header.match(/data:([^;]+)/);
    const mimeType = mimeMatch ? mimeMatch[1] : "application/octet-stream";
    const ext = mimeType.split("/")[1]?.replace("jpeg", "jpg") ?? "bin";
    const blob = new Blob([Uint8Array.from(atob(data), (c) => c.charCodeAt(0))], { type: mimeType });
    const blobUrl = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = blobUrl;
    a.download = `${assetId}.${ext}`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(blobUrl);
  } else {
    const a = document.createElement("a");
    a.href = url;
    a.download = assetId;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }
}
