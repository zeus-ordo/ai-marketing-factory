"use client";

import type { CampaignTask, ReviewItem } from "@/lib/api/campaigns";
import { useI18n } from "@/lib/i18n/context";
import { ProvenanceList } from "@/components/diagnostics/provenance-list";
import { sanitizeDiagnosticText } from "@/lib/campaign-diagnostics";

type Props = {
  items: ReviewItem[];
  campaignNameMap: Record<string, string>;
  campaignTaskMap: Record<string, CampaignTask[]>;
  loading: boolean;
  busy: boolean;
  selectedIds: string[];
  onToggleSelect: (reviewId: string, checked: boolean) => void;
  onToggleSelectAll: (checked: boolean) => void;
  onApprove: (item: ReviewItem) => void;
  onReject: (item: ReviewItem) => void;
  onPreview: (assetId: string) => void;
};

export function ReviewQueueTable({
  items,
  campaignNameMap,
  campaignTaskMap,
  loading,
  busy,
  selectedIds,
  onToggleSelect,
  onToggleSelectAll,
  onApprove,
  onReject,
  onPreview,
}: Props) {
  const { t } = useI18n();
  const pendingItems = items.filter((item) => item.status === "review_pending");
  const allSelected = pendingItems.length > 0 && pendingItems.every((item) => selectedIds.includes(item.review_id));

  if (loading) {
    return (
      <article className="rounded-2xl border border-slate-200 bg-white p-4 text-sm text-slate-500 dark:border-slate-800 dark:bg-slate-900">
        {t("review.loading")}
      </article>
    );
  }

  if (items.length === 0) {
    return (
      <article className="rounded-2xl border border-slate-200 bg-white p-4 text-sm text-slate-500 dark:border-slate-800 dark:bg-slate-900">
        {t("review.empty")}
      </article>
    );
  }

  return (
    <div className="overflow-x-auto rounded-2xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <table className="min-w-full table-auto text-left text-sm">
        <thead className="border-b border-slate-200 bg-slate-50 text-slate-500 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-400">
          <tr>
            <th className="px-4 py-3">
              <input
                type="checkbox"
                checked={allSelected}
                onChange={(event) => onToggleSelectAll(event.target.checked)}
                aria-label={t("review.selectedCount", { count: selectedIds.length })}
              />
            </th>
            <th className="px-4 py-3 whitespace-nowrap">{t("review.table.assetName")}</th>
            <th className="px-4 py-3">{t("review.table.asset")}</th>
            <th className="px-4 py-3">{t("review.table.campaign")}</th>
            <th className="min-w-[180px] px-4 py-3">{t("review.table.generation")}</th>
            <th className="min-w-[96px] px-4 py-3 whitespace-nowrap">{t("review.table.type")}</th>
            <th className="min-w-[110px] px-4 py-3 whitespace-nowrap">{t("review.table.status")}</th>
            <th className="px-4 py-3 whitespace-nowrap">{t("review.table.rejectReason")}</th>
            <th className="min-w-[150px] px-4 py-3 whitespace-nowrap">{t("review.table.actions")}</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.review_id} className="border-b border-slate-200/70 last:border-none dark:border-slate-800">
              <td className="px-4 py-3">
                <input
                  type="checkbox"
                  checked={selectedIds.includes(item.review_id)}
                  disabled={item.status !== "review_pending" || busy}
                  onChange={(event) => onToggleSelect(item.review_id, event.target.checked)}
                  aria-label={item.review_id}
                />
              </td>
              <td className="px-4 py-3">{assetName(item, campaignNameMap)}</td>
              <td className="px-4 py-3 font-mono text-xs text-slate-600 dark:text-slate-300">{item.asset_id}</td>
              <td className="px-4 py-3">
                <div className="font-medium">{campaignNameMap[item.campaign_id] || item.campaign_id}</div>
                <div className="font-mono text-[11px] text-slate-400">{item.campaign_id}</div>
              </td>
              <td className="px-4 py-3 text-xs">
                <code className="break-all text-slate-500">{item.generation_context_id || t("common.notAvailable")}</code>
                {item.source_summary ? <div className="mt-1 text-slate-500">{item.source_summary.internal_source_count}/{item.source_summary.external_source_count} {t("review.diagnostics.sources")} · {(item.source_summary.internal_ratio * 100).toFixed(1)}%/{(item.source_summary.external_ratio * 100).toFixed(1)}%</div> : null}
                {item.source_provenance?.length ? <div className="mt-1"><ProvenanceList sources={item.source_provenance} /></div> : null}
                {campaignTaskMap[item.campaign_id]?.filter((task) => task.task_type === ({ copy: "copywriting", image: "image_generation", video: "video_generation", ads: "ads_strategy" } as Record<string, string>)[item.asset_type || ""] && (!item.generation_context_id || task.generation_context_id === item.generation_context_id)).map((task) => <div key={task.task_id} className="mt-1 text-slate-500">{task.provider || t("common.notAvailable")}/{task.model || t("common.notAvailable")} · {sanitizeDiagnosticText(task.error_detail || task.error_class || task.blocked_reason || task.status)}</div>) }
              </td>
              <td className="min-w-[96px] px-4 py-3 whitespace-nowrap">
                {assetTypeLabel(item, t)}
              </td>
              <td className="px-4 py-3 whitespace-nowrap">
                <span className={`inline-flex whitespace-nowrap rounded-full px-2.5 py-1 text-xs font-semibold ${statusClasses(item.status)}`}>
                  {statusLabel(item.status, t)}
                </span>
              </td>
              <td className="px-4 py-3 text-xs text-slate-600 dark:text-slate-300">{rejectReason(item, t)}</td>
              <td className="px-4 py-3 whitespace-nowrap">
                <div className="flex flex-nowrap items-center gap-2 whitespace-nowrap">
                  <button
                    onClick={() => onPreview(item.asset_id)}
                    className="inline-flex shrink-0 whitespace-nowrap rounded-md bg-slate-900 px-2.5 py-1 text-xs font-medium text-white hover:bg-slate-700 dark:bg-slate-700"
                  >
                    預覽
                  </button>
                  <button
                    onClick={() => onApprove(item)}
                    disabled={busy || item.status !== "review_pending"}
                    className="inline-flex shrink-0 whitespace-nowrap rounded-md bg-emerald-600 px-2.5 py-1 text-xs font-medium text-white disabled:opacity-50"
                  >
                    {t("review.approve")}
                  </button>
                  <button
                    onClick={() => onReject(item)}
                    disabled={busy || item.status !== "review_pending"}
                    className="inline-flex shrink-0 whitespace-nowrap rounded-md bg-rose-600 px-2.5 py-1 text-xs font-medium text-white disabled:opacity-50"
                  >
                    {t("review.reject")}
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function statusClasses(status: ReviewItem["status"]) {
  if (status === "approved") return "bg-emerald-100 text-emerald-700";
  if (status === "rejected") return "bg-rose-100 text-rose-700";
  return "bg-amber-100 text-amber-700";
}

function statusLabel(status: ReviewItem["status"], t: ReturnType<typeof useI18n>["t"]) {
  if (status === "approved") return t("review.status.passed");
  if (status === "rejected") return t("review.status.rejected");
  return t("review.status.inReview");
}

function assetName(item: ReviewItem, campaignNameMap: Record<string, string>) {
  if (item.asset_name?.trim()) return item.asset_name;
  const campaignName = campaignNameMap[item.campaign_id] || item.campaign_id;
  const typeLabel = assetTypeName(item);
  return `${campaignName}${typeLabel ? ` · ${typeLabel}` : ""}`;
}

function assetTypeName(item: ReviewItem) {
  if (item.asset_type === "copy" || item.asset_id.startsWith("copy_")) return "文案";
  if (item.asset_type === "image" || item.asset_id.startsWith("img_") || item.asset_id.startsWith("image_")) return "圖片";
  if (item.asset_type === "video" || item.asset_id.startsWith("vid_") || item.asset_id.startsWith("video_")) return "影片";
  if (item.asset_type === "ads" || item.asset_id.startsWith("ads_")) return "廣告策略";
  return "";
}

function assetTypeLabel(item: ReviewItem, t: ReturnType<typeof useI18n>["t"]) {
  if (item.asset_type === "copy") return t("assets.type.copy");
  if (item.asset_type === "image") return t("assets.type.image");
  if (item.asset_type === "video") return t("assets.type.video");
  if (item.asset_type === "ads") return t("assets.type.ads");
  if (item.asset_id.startsWith("copy_")) return t("assets.type.copy");
  if (item.asset_id.startsWith("img_") || item.asset_id.startsWith("image_")) return t("assets.type.image");
  if (item.asset_id.startsWith("vid_") || item.asset_id.startsWith("video_")) return t("assets.type.video");
  if (item.asset_id.startsWith("ads_")) return t("assets.type.ads");
  return t("common.notAvailable");
}

function rejectReason(item: ReviewItem, t: ReturnType<typeof useI18n>["t"]) {
  return item.reject_reason || item.rejected_reason || item.reason || t("common.notAvailable");
}
