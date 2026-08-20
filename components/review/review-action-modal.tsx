"use client";

import { useState } from "react";
import { useI18n } from "@/lib/i18n/context";

type Props = {
  open: boolean;
  busy: boolean;
  onClose: () => void;
  onSubmit: (reason: string) => Promise<void>;
};

export function ReviewActionModal({ open, busy, onClose, onSubmit }: Props) {
  const { t } = useI18n();
  const [reason, setReason] = useState("");

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-lg rounded-2xl bg-white p-4 shadow-xl dark:bg-slate-900">
        <h3 className="text-lg font-semibold">{t("review.rejectReason")}</h3>
        <textarea
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          placeholder={t("review.rejectReasonPlaceholder")}
          className="mt-3 h-28 w-full rounded-xl border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
        />
        <div className="mt-4 flex justify-end gap-2">
          <button
            onClick={onClose}
            disabled={busy}
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700"
          >
            {t("review.cancel")}
          </button>
          <button
            onClick={() => onSubmit(reason.trim())}
            disabled={busy || reason.trim().length === 0}
            className="rounded-lg bg-rose-600 px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            {t("review.reject")}
          </button>
        </div>
      </div>
    </div>
  );
}
