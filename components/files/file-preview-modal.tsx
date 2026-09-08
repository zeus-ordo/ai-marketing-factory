/* eslint-disable react-hooks/set-state-in-effect -- synchronize preview text with selected source */
"use client";

import { useEffect, useMemo, useState } from "react";
import { useI18n } from "@/lib/i18n/context";

type Props = {
  source: File | string | null;
  fileName: string;
  open: boolean;
  onClose: () => void;
};

export function FilePreviewModal({ source, fileName, open, onClose }: Props) {
  const { t } = useI18n();
  const [text, setText] = useState<string | null>(null);
  const sourceUrl = useMemo(() => {
    if (!source) return null;
    return source instanceof File ? URL.createObjectURL(source) : source;
  }, [source]);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const mimeType = source instanceof File ? source.type : mimeFromName(fileName);
  const kind = previewKind(mimeType, fileName);

  useEffect(() => {
    if (!sourceUrl) {
      setPreviewUrl(null);
      return;
    }
    if (source instanceof File) {
      setPreviewUrl(sourceUrl);
      return;
    }
    let active = true;
    let objectUrl: string | null = null;
    const token = typeof window !== "undefined" ? localStorage.getItem("access_token") : null;
    fetch(sourceUrl, { headers: token ? { Authorization: `Bearer ${token}` } : undefined })
      .then((response) => {
        if (!response.ok) throw new Error(`Preview request failed: ${response.status}`);
        return response.blob();
      })
      .then((blob) => {
        if (!active) return;
        objectUrl = URL.createObjectURL(blob);
        setPreviewUrl(objectUrl);
      })
      .catch(() => { if (active) setPreviewUrl(null); });
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [source, sourceUrl]);

  useEffect(() => {
    return () => {
      if (source instanceof File && sourceUrl) URL.revokeObjectURL(sourceUrl);
    };
  }, [source, sourceUrl]);

  useEffect(() => {
    if (!open || !source || !previewUrl || kind !== "text") {
      setText(null);
      return;
    }
    let cancelled = false;
    fetch(previewUrl).then((response) => response.text()).then((value) => { if (!cancelled) setText(value); }).catch(() => { if (!cancelled) setText(null); });
    return () => { cancelled = true; };
  }, [kind, open, previewUrl, source]);

  if (!open || !previewUrl) return null;

  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center bg-black/60 p-4" onClick={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <div className="flex max-h-[90vh] w-full max-w-4xl flex-col overflow-hidden rounded-2xl bg-white shadow-2xl dark:bg-slate-900">
        <header className="flex items-center justify-between gap-3 border-b border-slate-200 px-5 py-3 dark:border-slate-700">
          <h2 className="truncate text-sm font-semibold">{fileName}</h2>
          <div className="flex items-center gap-2">
            <a href={previewUrl} download={fileName} target="_blank" rel="noreferrer" className="rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-medium text-white">{t("campaigns.knowledge.download")}</a>
            <button type="button" onClick={onClose} className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs dark:border-slate-700">{t("common.cancel")}</button>
          </div>
        </header>
        <div className="min-h-56 overflow-auto bg-slate-50 p-4 dark:bg-slate-950">
          {kind === "image" ? <img src={previewUrl} alt={fileName} className="mx-auto max-h-[70vh] max-w-full object-contain" /> : null}
          {kind === "video" ? <video src={previewUrl} controls className="mx-auto max-h-[70vh] max-w-full" /> : null}
          {kind === "pdf" ? <iframe src={previewUrl} title={fileName} className="h-[70vh] w-full rounded-lg bg-white" /> : null}
          {kind === "text" ? <pre className="whitespace-pre-wrap text-sm text-slate-700 dark:text-slate-300">{text ?? t("campaigns.form.notAttachable")}</pre> : null}
          {kind === "other" ? <div className="flex h-56 items-center justify-center text-sm text-slate-500">{t("campaigns.form.notAttachable")}</div> : null}
        </div>
      </div>
    </div>
  );
}

type PreviewKind = "image" | "video" | "pdf" | "text" | "other";

function previewKind(mimeType: string, fileName: string): PreviewKind {
  if (mimeType.startsWith("image/") || /\.(png|jpe?g|gif|webp|svg)$/i.test(fileName)) return "image";
  if (mimeType.startsWith("video/") || /\.(mp4|webm|ogg|mov)$/i.test(fileName)) return "video";
  if (mimeType === "application/pdf" || /\.pdf$/i.test(fileName)) return "pdf";
  if (mimeType.startsWith("text/") || /\.(txt|md|csv|json|xml)$/i.test(fileName)) return "text";
  return "other";
}

function mimeFromName(fileName: string): string {
  if (/\.pdf$/i.test(fileName)) return "application/pdf";
  if (/\.(png|jpe?g|gif|webp|svg)$/i.test(fileName)) return "image/*";
  if (/\.(mp4|webm|ogg|mov)$/i.test(fileName)) return "video/*";
  if (/\.(txt|md|csv|json|xml)$/i.test(fileName)) return "text/plain";
  return "application/octet-stream";
}
