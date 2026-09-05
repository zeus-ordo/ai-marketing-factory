"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ReviewActionModal } from "@/components/review/review-action-modal";
import { ReviewAssetPreviewModal } from "@/components/review/review-asset-preview-modal";
import { ReviewAuditLog } from "@/components/review/review-audit-log";
import { ReviewQueueTable } from "@/components/review/review-queue-table";
import { ProvenanceList } from "@/components/diagnostics/provenance-list";
import { canRetryTask, sanitizeDiagnosticText } from "@/lib/campaign-diagnostics";
import {
  approveReviewItem,
  listCampaigns,
  listReviewAuditLogs,
  listReviewQueue,
  rejectReviewItem,
  type ReviewAuditEntry,
  type ReviewItem,
  type ReviewStatus,
  type CampaignTask,
} from "@/lib/api/campaigns";
import { useAuth } from "@/lib/auth/context";
import { useI18n } from "@/lib/i18n/context";

function diagnosticTaskTypeLabel(taskType: string, t: ReturnType<typeof useI18n>["t"]) {
  if (taskType === "copywriting") return t("review.diagnostics.copywriting");
  if (taskType === "image_generation") return t("review.diagnostics.imageGeneration");
  if (taskType === "video_generation") return t("review.diagnostics.videoGeneration");
  if (taskType === "ads_strategy") return t("review.diagnostics.adsStrategy");
  return taskType;
}

function diagnosticTaskStatusLabel(status: string, t: ReturnType<typeof useI18n>["t"]) {
  if (status === "pending") return t("status.pending");
  if (status === "planned") return t("status.planned");
  if (status === "running") return t("status.running");
  if (status === "validating") return t("status.validating");
  if (status === "passed") return t("status.passed");
  if (status === "retrying") return t("status.retrying");
  if (status === "failed") return t("status.failed");
  if (status === "blocked") return t("status.blocked");
  return t("common.notAvailable");
}

export default function ReviewPage() {
  const { t } = useI18n();
  const { user, isLoading: authLoading } = useAuth();
  const canReview = user?.permissions.some((permission) => ["*", "admin", "platform:admin", "review:approve", "review:reject", "review:revision"].includes(permission)) ?? false;
  const [items, setItems] = useState<ReviewItem[]>([]);
  const [campaignNameMap, setCampaignNameMap] = useState<Record<string, string>>({});
  const [campaignTaskMap, setCampaignTaskMap] = useState<Record<string, CampaignTask[]>>({});
  const [logs, setLogs] = useState<ReviewAuditEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<"" | ReviewStatus>("");
  const [query, setQuery] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [rejectTarget, setRejectTarget] = useState<ReviewItem | null>(null);
  const [previewTarget, setPreviewTarget] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const latestRequestId = useRef(0);

  const fetchAllReviewItems = useCallback(async () => {
    const pageSize = 200;
    const maxPages = 20;
    let page = 1;
    let total = 0;
    const all: ReviewItem[] = [];

    do {
      const chunk = await listReviewQueue({
        page,
        pageSize,
        status: statusFilter || undefined,
      });
      all.push(...chunk.items);
      total = chunk.total;
      page += 1;
      if (chunk.items.length === 0) break;
    } while (all.length < total && page <= maxPages);

    return all;
  }, [statusFilter]);

  const loadData = useCallback(async (options?: { showLoading?: boolean }) => {
    const requestId = latestRequestId.current + 1;
    latestRequestId.current = requestId;
    const showLoading = options?.showLoading ?? items.length === 0;

    if (showLoading) {
      setLoading(true);
    }
    setMessage(null);
    try {
      const [queueItems, audit, campaigns] = await Promise.all([
        fetchAllReviewItems(),
        listReviewAuditLogs({ page: 1, pageSize: 10 }),
        listCampaigns(),
      ]);
      if (requestId !== latestRequestId.current) return;
      setItems(queueItems);
      setLogs(audit.items);
      setCampaignNameMap(Object.fromEntries(campaigns.map((campaign) => [campaign.campaign_id, campaign.brief.campaign_name])));
      setCampaignTaskMap(Object.fromEntries(campaigns.map((campaign) => [campaign.campaign_id, campaign.tasks ?? []])));
      setSelectedIds((prev) => prev.filter((id) => queueItems.some((item) => item.review_id === id)));
    } catch {
      if (requestId === latestRequestId.current) {
        setMessage(t("review.loadFailed"));
      }
    } finally {
      if (requestId === latestRequestId.current) {
        setLoading(false);
      }
    }
  }, [fetchAllReviewItems, items.length, t]);

  useEffect(() => {
    if (authLoading || !canReview) return;
    const timer = window.setTimeout(() => {
      void loadData({ showLoading: true });
    }, 0);

    return () => {
      window.clearTimeout(timer);
    };
  }, [authLoading, canReview, loadData]);

  // Auto-refresh review queue every 30 seconds to pick up new items
  useEffect(() => {
    if (busy || authLoading || !canReview) return;
    const interval = window.setInterval(() => {
      void loadData({ showLoading: false });
    }, 30_000);
    return () => {
      window.clearInterval(interval);
    };
  }, [loadData, busy, authLoading, canReview]);

  async function handleApprove(item: ReviewItem) {
    if (!window.confirm(t("review.confirmApprove"))) return;
    setBusy(true);
    try {
      await approveReviewItem(item.review_id, "admin");
      setMessage(t("review.approveSuccess"));
      await loadData({ showLoading: false });
    } catch {
      setMessage(t("review.approveFailed"));
    } finally {
      setBusy(false);
    }
  }

  async function handleApproveSelected() {
    const candidates = filteredItems.filter((item) => selectedIds.includes(item.review_id) && item.status === "review_pending");
    if (candidates.length === 0) {
      setMessage(t("review.noPendingSelected"));
      return;
    }

    setBusy(true);
    try {
      await Promise.all(candidates.map((item) => approveReviewItem(item.review_id, "admin")));
      setMessage(t("review.bulkApproveSuccess"));
      await loadData({ showLoading: false });
    } catch {
      setMessage(t("review.bulkApproveFailed"));
    } finally {
      setBusy(false);
    }
  }

  async function handleRejectSubmit(reason: string) {
    if (!rejectTarget) return;
    setBusy(true);
    try {
      await rejectReviewItem(rejectTarget.review_id, reason, "admin");
      setMessage(t("review.rejectSuccess"));
      setRejectTarget(null);
      await loadData({ showLoading: false });
    } catch {
      setMessage(t("review.rejectFailed"));
    } finally {
      setBusy(false);
    }
  }

  const summary = useMemo(() => {
    const pending = items.filter((item) => item.status === "review_pending").length;
    const approved = items.filter((item) => item.status === "approved").length;
    const rejected = items.filter((item) => item.status === "rejected").length;
    return { pending, approved, rejected };
  }, [items]);

  if (authLoading) {
    return <section className="rounded-2xl border border-slate-200 bg-white p-6 text-sm text-slate-500 dark:border-slate-800 dark:bg-slate-900">{t("common.loading")}</section>;
  }

  if (!canReview) {
    return <section className="rounded-2xl border border-slate-200 bg-white p-6 text-sm text-slate-500 dark:border-slate-800 dark:bg-slate-900">{t("roles.noPermission")}</section>;
  }

  const normalizedQuery = query.trim().toLowerCase();
  const filteredItems = items.filter((item) => {
    if (statusFilter && item.status !== statusFilter) return false;
    if (!normalizedQuery) return true;
    const assetName = getReviewAssetName(item).toLowerCase();
    const campaignName = (campaignNameMap[item.campaign_id] || "").toLowerCase();
    const rejectedReason = getRejectedReason(item).toLowerCase();
    return item.asset_id.toLowerCase().includes(normalizedQuery) ||
      item.campaign_id.toLowerCase().includes(normalizedQuery) ||
      campaignName.includes(normalizedQuery) ||
      assetName.includes(normalizedQuery) ||
      rejectedReason.includes(normalizedQuery);
  });

  function toggleSelect(reviewId: string, checked: boolean) {
    setSelectedIds((prev) => {
      if (checked) return Array.from(new Set([...prev, reviewId]));
      return prev.filter((id) => id !== reviewId);
    });
  }

  function toggleSelectAll(checked: boolean) {
    if (!checked) {
      setSelectedIds([]);
      return;
    }

    setSelectedIds(filteredItems.filter((item) => item.status === "review_pending").map((item) => item.review_id));
  }

  return (
    <section className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">{t("review.title")}</h1>
        <p className="text-sm text-slate-500">{t("review.subtitle")}</p>
      </header>

      {message ? <p className="rounded-xl bg-blue-50 px-3 py-2 text-sm text-blue-700">{message}</p> : null}

      <div className="grid gap-4 rounded-2xl border border-slate-200 bg-white p-4 md:grid-cols-3 dark:border-slate-800 dark:bg-slate-900">
        <Metric title={t("review.status.inReview")} value={summary.pending} tone="text-amber-500" />
        <Metric title={t("review.status.passed")} value={summary.approved} tone="text-emerald-500" />
        <Metric title={t("review.status.rejected")} value={summary.rejected} tone="text-rose-500" />
      </div>

      {Array.from(new Map(items.filter((item) => item.source_summary).map((item) => [`${item.campaign_id}:${item.run_id || item.generation_context_id}`, item] as const)).values()).map((diagnosticItem) => {
        const summary = diagnosticItem.source_summary;
        if (!summary) return null;
        const source_provenance = diagnosticItem.source_provenance?.length ? diagnosticItem.source_provenance : summary.provenance;
        const groupTasks = campaignTaskMap[diagnosticItem.campaign_id]?.filter((task) =>
          (task.status === "failed" || task.status === "blocked") &&
          (!diagnosticItem.run_id || task.run_id === diagnosticItem.run_id) &&
          (!summary.generation_context_id || task.generation_context_id === summary.generation_context_id)
        ) ?? [];
        return (
          <section key={`${diagnosticItem.campaign_id}:${diagnosticItem.run_id || summary.generation_context_id}`} aria-label={t("review.diagnostics.title")} className="space-y-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h2 className="text-sm font-semibold">{t("review.diagnostics.title")}</h2>
              <code className="break-all text-xs text-slate-500">{campaignNameMap[diagnosticItem.campaign_id] || diagnosticItem.campaign_id} · {summary.generation_context_id}</code>
            </div>
            <div className="grid gap-3 text-xs sm:grid-cols-2 lg:grid-cols-4">
              <div><p className="text-slate-500">{t("review.diagnostics.internalSources")}</p><p className="font-medium">{summary.internal_source_count} · {summary.internal_token_count} {t("review.diagnostics.tokens")}</p></div>
              <div><p className="text-slate-500">{t("review.diagnostics.externalSources")}</p><p className="font-medium">{summary.external_source_count} · {summary.external_token_count} {t("review.diagnostics.tokens")}</p></div>
              <div><p className="text-slate-500">{t("review.diagnostics.ratios")}</p><p className="font-medium">{(summary.internal_ratio * 100).toFixed(1)}% / {(summary.external_ratio * 100).toFixed(1)}%</p></div>
              <div><p className="text-slate-500">{t("review.diagnostics.selectedReferences")}</p><p className="break-words font-medium">{summary.selected_reference_ids.join(", ") || t("common.notAvailable")}</p></div>
            </div>
            <ProvenanceList sources={source_provenance} />
            {groupTasks.map((task) => (
              <p key={task.task_id} className="text-xs text-slate-600 dark:text-slate-300">{diagnosticTaskTypeLabel(task.task_type, t)}: {task.provider || t("common.notAvailable")}/{task.model || t("common.notAvailable")} · {sanitizeDiagnosticText(task.error_detail || task.error_class || task.blocked_reason || diagnosticTaskStatusLabel(task.status, t))} · {t("review.diagnostics.retryable")}: {canRetryTask(task) ? t("common.yes") : t("common.no")} · {t("review.diagnostics.attempts")}: {task.retry_count ?? 0}{task.next_retry_at ? ` · ${task.next_retry_at}` : ""}</p>
            ))}
          </section>
        );
      })}

      <div className="grid gap-3 rounded-2xl border border-slate-200 bg-white p-4 md:grid-cols-2 dark:border-slate-800 dark:bg-slate-900">
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder={t("review.searchPlaceholder")}
          aria-label={t("review.searchPlaceholder")}
          className="rounded-xl border border-slate-200 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
        />
        <select
          id="review-status-filter"
          value={statusFilter}
          onChange={(event) => setStatusFilter(event.target.value as "" | ReviewStatus)}
          aria-label={t("review.allStatus")}
          className="rounded-xl border border-slate-200 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
        >
          <option value="">{t("review.allStatus")}</option>
          <option value="review_pending">{t("review.status.inReview")}</option>
          <option value="approved">{t("review.status.passed")}</option>
          <option value="rejected">{t("review.status.rejected")}</option>
        </select>
      </div>

      <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm dark:border-slate-800 dark:bg-slate-900">
        <span className="text-slate-500">{t("review.selectedCount", { count: selectedIds.length })}</span>
        <button
          onClick={handleApproveSelected}
          disabled={busy || selectedIds.length === 0}
          className="rounded-lg bg-emerald-600 px-2.5 py-1.5 text-xs font-medium text-white disabled:opacity-50"
        >
          {t("review.approveSelected")}
        </button>
        <button
          onClick={() => setSelectedIds([])}
          disabled={selectedIds.length === 0}
          className="rounded-lg border border-slate-300 px-2.5 py-1.5 text-xs font-medium disabled:opacity-50 dark:border-slate-700"
        >
          {t("review.clearSelection")}
        </button>
      </div>

      <ReviewQueueTable
        items={filteredItems}
        campaignNameMap={campaignNameMap}
        campaignTaskMap={campaignTaskMap}
        loading={loading}
        busy={busy}
        selectedIds={selectedIds}
        onToggleSelect={toggleSelect}
        onToggleSelectAll={toggleSelectAll}
        onApprove={handleApprove}
        onReject={(item) => setRejectTarget(item)}
        onPreview={(assetId) => setPreviewTarget(assetId)}
      />

      <ReviewAuditLog items={logs} />

      <ReviewActionModal
        key={rejectTarget?.review_id ?? "review-reject-modal"}
        open={Boolean(rejectTarget)}
        busy={busy}
        onClose={() => setRejectTarget(null)}
        onSubmit={handleRejectSubmit}
      />

      <ReviewAssetPreviewModal
        assetId={previewTarget}
        open={Boolean(previewTarget)}
        onClose={() => setPreviewTarget(null)}
        showRegenerate={false}
      />
    </section>
  );
}

function getReviewAssetName(item: ReviewItem) {
  if (item.asset_name?.trim()) return item.asset_name;
  if (item.asset_type === "copy" || item.asset_id.startsWith("copy_")) return "文案";
  if (item.asset_type === "image" || item.asset_id.startsWith("img_") || item.asset_id.startsWith("image_")) return "圖片";
  if (item.asset_type === "video" || item.asset_id.startsWith("vid_") || item.asset_id.startsWith("video_")) return "影片";
  return item.asset_id;
}

function getRejectedReason(item: ReviewItem) {
  return item.reject_reason || item.rejected_reason || item.reason || "";
}

function Metric({ title, value, tone }: { title: string; value: number; tone: string }) {
  return (
    <div>
      <p className="text-xs text-slate-500">{title}</p>
      <p className={`text-2xl font-semibold ${tone}`}>{value}</p>
    </div>
  );
}
