"use client";

import { useEffect, useMemo, useState } from "react";
import {
  getCampaignBundle,
  listCampaigns,
  listValidationResults,
  type CampaignStatus,
} from "@/lib/api/campaigns";
import { useI18n } from "@/lib/i18n/context";
import { formatDateTime } from "@/lib/i18n/format";

type AssetType = "image" | "video" | "copy";

type PerformanceRow = {
  campaignId: string;
  campaignName: string;
  assetId: string;
  type: AssetType;
  score: number | null;
  validationResult: "passed" | "failed" | null;
  status: CampaignStatus;
  createdAt: string;
  runId?: string;
};

type ViewMode = "flat" | "byRun";

export default function PerformancePage() {
  const { t, locale } = useI18n();
  const [rows, setRows] = useState<PerformanceRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [campaignFilter, setCampaignFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState<"" | AssetType>("");
  const [viewMode, setViewMode] = useState<ViewMode>("flat");

  useEffect(() => {
    let mounted = true;

    async function loadPerformance() {
      setLoading(true);
      setMessage(null);
      try {
        const campaigns = await listCampaigns();
        const settled = await Promise.allSettled(
          campaigns.map(async (campaign): Promise<PerformanceRow[]> => {
            const [bundle, validations] = await Promise.all([
              getCampaignBundle(campaign.campaign_id),
              listValidationResults(campaign.campaign_id),
            ]);

            const scoreMap = new Map(validations.map((item) => [item.asset_id, item.score]));
            const resultMap = new Map(validations.map((item) => [item.asset_id, item.result]));
            const runIdMap = new Map<string, string>(validations.map((v) => [v.asset_id, v.run_id ?? ""]));
            const rows: PerformanceRow[] = [];

            for (const asset of bundle.image_assets) {
              const runId = runIdMap.get(asset.asset_id);
              rows.push({
                campaignId: campaign.campaign_id,
                campaignName: campaign.brief.campaign_name,
                assetId: asset.asset_id,
                type: "image",
                score: typeof asset.score === "number" ? asset.score : scoreMap.get(asset.asset_id) ?? null,
                validationResult: resultMap.get(asset.asset_id) ?? null,
                status: campaign.status,
                createdAt: campaign.created_at,
                runId: runId || undefined,
              });
            }

            for (const asset of bundle.video_assets) {
              const runId = runIdMap.get(asset.asset_id);
              rows.push({
                campaignId: campaign.campaign_id,
                campaignName: campaign.brief.campaign_name,
                assetId: asset.asset_id,
                type: "video",
                score: typeof asset.score === "number" ? asset.score : scoreMap.get(asset.asset_id) ?? null,
                validationResult: resultMap.get(asset.asset_id) ?? null,
                status: campaign.status,
                createdAt: campaign.created_at,
                runId: runId || undefined,
              });
            }

            for (const asset of bundle.copy_assets) {
              rows.push({
                campaignId: campaign.campaign_id,
                campaignName: campaign.brief.campaign_name,
                assetId: asset.variant_id,
                type: "copy",
                score: null,
                validationResult: null,
                status: campaign.status,
                createdAt: campaign.created_at,
                runId: undefined,
              });
            }

            return rows;
          }),
        );

        const aggregated: PerformanceRow[] = settled.flatMap((item) => (item.status === "fulfilled" ? item.value : []));
        if (settled.some((item) => item.status === "rejected")) {
          setMessage(t("performance.fallback"));
        }

        if (!mounted) return;
        setRows(aggregated);
      } catch {
        if (!mounted) return;
        setRows([]);
        setMessage(t("performance.fallback"));
      } finally {
        if (mounted) setLoading(false);
      }
    }

    loadPerformance();
    return () => {
      mounted = false;
    };
  }, [t]);

  const campaignOptions = useMemo(() => {
    const unique = new Map<string, string>();
    for (const row of rows) {
      if (!unique.has(row.campaignId)) {
        unique.set(row.campaignId, row.campaignName);
      }
    }
    return Array.from(unique.entries()).map(([id, name]) => ({ id, name }));
  }, [rows]);

  const filteredRows = useMemo(() => {
    const base = rows.filter((row) => {
      if (campaignFilter && row.campaignId !== campaignFilter) return false;
      if (typeFilter && row.type !== typeFilter) return false;
      return true;
    });
    if (viewMode === "byRun") {
      return [...base].sort((a, b) => {
        const aKey = a.runId ?? "";
        const bKey = b.runId ?? "";
        if (aKey < bKey) return -1;
        if (aKey > bKey) return 1;
        return a.campaignId.localeCompare(b.campaignId);
      });
    }
    return base;
  }, [rows, campaignFilter, typeFilter, viewMode]);

  const metrics = useMemo(() => {
    const campaignCount = new Set(filteredRows.map((row) => row.campaignId)).size;
    const assetCount = filteredRows.length;
    const scoredRows = filteredRows.filter((row) => row.score !== null);
    const avgScore = scoredRows.length > 0
      ? scoredRows.reduce((sum, row) => sum + (row.score ?? 0), 0) / scoredRows.length
      : 0;
    const evaluatedRows = filteredRows.filter((row) => row.validationResult !== null);
    const passedCount = evaluatedRows.filter((row) => row.validationResult === "passed").length;
    const passRate = evaluatedRows.length > 0 ? passedCount / evaluatedRows.length : 0;
    return { campaignCount, assetCount, avgScore, passRate };
  }, [filteredRows]);

  return (
    <section className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">{t("performance.title")}</h1>
        <p className="text-sm text-slate-500">{t("performance.subtitle")}</p>
      </header>

      {message ? (
        <p className="rounded-xl bg-amber-50 px-3 py-2 text-sm text-amber-700">{message}</p>
      ) : null}

      <div className="grid gap-4 rounded-2xl border border-slate-200 bg-white p-4 md:grid-cols-4 dark:border-slate-800 dark:bg-slate-900">
        <Metric title={t("performance.metric.campaigns")} value={String(metrics.campaignCount)} tone="text-blue-600" />
        <Metric title={t("performance.metric.assets")} value={String(metrics.assetCount)} tone="text-violet-600" />
        <Metric title={t("performance.metric.avgScore")} value={`${Math.round(metrics.avgScore * 100)}%`} tone="text-emerald-500" />
        <Metric title={t("performance.metric.passRate")} value={`${Math.round(metrics.passRate * 100)}%`} tone="text-amber-500" />
      </div>

      <div className="grid gap-3 rounded-2xl border border-slate-200 bg-white p-4 md:grid-cols-5 dark:border-slate-800 dark:bg-slate-900">
        <select
          value={campaignFilter}
          onChange={(event) => setCampaignFilter(event.target.value)}
          aria-label={t("performance.filter.campaign")}
          className="rounded-xl border border-slate-200 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
        >
          <option value="">{t("common.allCampaigns")}</option>
          {campaignOptions.map((item) => (
            <option key={item.id} value={item.id}>{item.name}</option>
          ))}
        </select>

        <select
          value={typeFilter}
          onChange={(event) => setTypeFilter(event.target.value as "" | AssetType)}
          aria-label={t("performance.filter.type")}
          className="rounded-xl border border-slate-200 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
        >
          <option value="">{t("performance.filter.allTypes")}</option>
          <option value="image">{t("assets.type.image")}</option>
          <option value="video">{t("assets.type.video")}</option>
          <option value="copy">{t("assets.type.copy")}</option>
        </select>

        <div className="flex gap-1">
          <button
            onClick={() => setViewMode("flat")}
            className={`flex-1 rounded-xl px-3 py-2 text-sm font-medium ${viewMode === "flat" ? "bg-slate-900 text-white dark:bg-slate-700" : "border border-slate-200 dark:border-slate-700 dark:bg-slate-950"}`}
          >
            {t("performance.viewFlat")}
          </button>
          <button
            onClick={() => setViewMode("byRun")}
            className={`flex-1 rounded-xl px-3 py-2 text-sm font-medium ${viewMode === "byRun" ? "bg-slate-900 text-white dark:bg-slate-700" : "border border-slate-200 dark:border-slate-700 dark:bg-slate-950"}`}
          >
            {t("performance.viewByRun")}
          </button>
        </div>

        <button
          onClick={() => {
            setCampaignFilter("");
            setTypeFilter("");
          }}
          className="rounded-xl bg-slate-900 px-3 py-2 text-sm font-medium text-white dark:bg-slate-700"
        >
          {t("common.apply")}
        </button>

        <button
          onClick={() => {
            const csv = toCsv(filteredRows);
            downloadCsv(csv, `performance-${new Date().toISOString().slice(0, 10)}.csv`);
          }}
          className="rounded-xl border border-emerald-600 px-3 py-2 text-sm font-medium text-emerald-600 dark:border-emerald-500 dark:text-emerald-400"
        >
          {t("performance.exportCsv")}
        </button>
      </div>

      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <table className="min-w-full text-left text-sm">
          <thead className="border-b border-slate-200 bg-slate-50 text-slate-500 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-400">
            <tr>
              <th className="px-4 py-3">{t("performance.table.campaign")}</th>
              <th className="px-4 py-3">{t("performance.table.asset")}</th>
              <th className="px-4 py-3">{t("performance.table.run")}</th>
              <th className="px-4 py-3">{t("performance.table.type")}</th>
              <th className="px-4 py-3">{t("performance.table.score")}</th>
              <th className="px-4 py-3">{t("performance.table.result")}</th>
              <th className="px-4 py-3">{t("performance.table.created")}</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td className="px-4 py-6 text-center text-slate-500" colSpan={7}>{t("performance.loading")}</td>
              </tr>
            ) : filteredRows.length === 0 ? (
              <tr>
                <td className="px-4 py-6 text-center text-slate-500" colSpan={7}>{t("performance.empty")}</td>
              </tr>
            ) : filteredRows.map((row) => (
              <tr key={`${row.campaignId}-${row.assetId}`} className="border-b border-slate-200/70 last:border-none dark:border-slate-800">
                <td className="px-4 py-3 font-medium">{row.campaignName}</td>
                <td className="px-4 py-3">{row.assetId}</td>
                <td className="px-4 py-3">
                  {row.runId ? (
                    <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs font-mono text-slate-600 dark:bg-slate-800 dark:text-slate-400">
                      {row.runId.slice(0, 12)}…
                    </span>
                  ) : (
                    <span className="text-slate-400">—</span>
                  )}
                </td>
                <td className="px-4 py-3">{typeLabel(row.type, t)}</td>
                <td className="px-4 py-3">{row.score === null ? t("common.notAvailable") : `${Math.round(row.score * 100)}%`}</td>
                <td className="px-4 py-3">
                  <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${resultClass(row.validationResult)}`}>
                    {resultLabel(row.validationResult, t)}
                  </span>
                </td>
                <td className="px-4 py-3">{formatDateTime(locale, row.createdAt)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Metric({ title, value, tone }: { title: string; value: string; tone: string }) {
  return (
    <div>
      <p className="text-xs text-slate-500">{title}</p>
      <p className={`text-2xl font-semibold ${tone}`}>{value}</p>
    </div>
  );
}

function typeLabel(type: AssetType, t: ReturnType<typeof useI18n>["t"]) {
  if (type === "image") return t("assets.type.image");
  if (type === "video") return t("assets.type.video");
  return t("assets.type.copy");
}

function resultLabel(result: "passed" | "failed" | null, t: ReturnType<typeof useI18n>["t"]) {
  if (result === null) return t("performance.result.noScore");
  if (result === "passed") return t("performance.result.passed");
  return t("performance.result.failed");
}

function resultClass(result: "passed" | "failed" | null) {
  if (result === null) return "bg-slate-100 text-slate-700";
  if (result === "passed") return "bg-emerald-100 text-emerald-700";
  return "bg-rose-100 text-rose-700";
}

function toCsv(rows: PerformanceRow[]): string {
  const header = ["Campaign", "Asset ID", "Run ID", "Type", "Score", "Result", "Status", "Created At"];
  const csvRows = rows.map((row) => [
    row.campaignName,
    row.assetId,
    row.runId ?? "",
    row.type,
    row.score !== null ? String(Math.round(row.score * 100)) : "",
    row.validationResult ?? "",
    row.status,
    row.createdAt,
  ]);
  return [header, ...csvRows]
    .map((line) => line.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(","))
    .join("\n");
}

function downloadCsv(csv: string, filename: string) {
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}
