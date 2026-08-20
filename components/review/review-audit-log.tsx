"use client";

import { formatDateTime } from "@/lib/i18n/format";
import { useI18n } from "@/lib/i18n/context";
import type { ReviewAuditEntry } from "@/lib/api/campaigns";

type Props = {
  items: ReviewAuditEntry[];
};

export function ReviewAuditLog({ items }: Props) {
  const { t, locale } = useI18n();

  return (
    <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <header className="border-b border-slate-200 px-4 py-3 text-sm font-semibold dark:border-slate-800">
        {t("review.auditTitle")}
      </header>
      <div className="max-h-[280px] overflow-auto">
        <table className="min-w-full text-left text-xs">
          <thead className="border-b border-slate-200 bg-slate-50 text-slate-500 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-400">
            <tr>
              <th className="px-4 py-2">{t("review.table.time")}</th>
              <th className="px-4 py-2">{t("review.table.operator")}</th>
              <th className="px-4 py-2">{t("review.table.action")}</th>
              <th className="px-4 py-2">{t("review.table.target")}</th>
              <th className="px-4 py-2">{t("review.table.result")}</th>
            </tr>
          </thead>
          <tbody>
            {items.length === 0 ? (
              <tr>
                <td className="px-4 py-3 text-slate-500" colSpan={5}>{t("review.auditEmpty")}</td>
              </tr>
            ) : items.map((item, index) => (
              <tr key={`${item.timestamp}-${item.target}-${index}`} className="border-b border-slate-200/70 last:border-none dark:border-slate-800">
                <td className="px-4 py-2">{formatDateTime(locale, item.timestamp)}</td>
                <td className="px-4 py-2">{item.operator}</td>
                <td className="px-4 py-2">{actionLabel(item.action, t)}</td>
                <td className="px-4 py-2">{item.target}</td>
                <td className="px-4 py-2">
                  <span className={`rounded-full px-2 py-0.5 ${resultBadgeClasses(item.result)}`}>
                    {resultLabel(item.result, t)}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function actionLabel(action: ReviewAuditEntry["action"], t: ReturnType<typeof useI18n>["t"]) {
  if (action === "approve") return t("review.action.approve");
  return t("review.action.reject");
}

function resultLabel(result: ReviewAuditEntry["result"], t: ReturnType<typeof useI18n>["t"]) {
  if (result === "ok") return t("review.result.ok");
  if (result === "failed") return t("review.result.failed");
  return t("review.result.rateLimited");
}

function resultBadgeClasses(result: ReviewAuditEntry["result"]) {
  if (result === "ok") return "bg-emerald-100 text-emerald-700";
  if (result === "failed") return "bg-rose-100 text-rose-700";
  return "bg-amber-100 text-amber-700";
}
