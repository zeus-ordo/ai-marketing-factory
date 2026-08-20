"use client";

import { useEffect, useMemo, useState } from "react";
import { getCampaignBundle, listCampaigns, listValidationResults, uploadManualAsset, type CampaignRecord, type CampaignStatus } from "@/lib/api/campaigns";
import { useI18n } from "@/lib/i18n/context";

type AssetType = "image" | "video" | "copy";

type AssetRow = {
  assetId: string;
  campaignId: string;
  campaignName: string;
  type: AssetType;
  score: number | null;
  status: CampaignStatus;
  url: string | null;
  text: string | null;
};

export default function AssetsPage() {
  const { t } = useI18n();
  const [rows, setRows] = useState<AssetRow[]>([]);
  const [campaigns, setCampaigns] = useState<CampaignRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [queryDraft, setQueryDraft] = useState("");
  const [typeDraft, setTypeDraft] = useState<"" | AssetType>("");
  const [validationDraft, setValidationDraft] = useState<"" | "passed" | "failed">("");
  const [query, setQuery] = useState("");
  const [typeFilter, setTypeFilter] = useState<"" | AssetType>("");
  const [validationFilter, setValidationFilter] = useState<"" | "passed" | "failed">("");
  const [manualCampaignId, setManualCampaignId] = useState("");
  const [manualType, setManualType] = useState<AssetType>("image");
  const [manualPrompt, setManualPrompt] = useState("");
  const [manualFile, setManualFile] = useState<File | null>(null);
  const [manualFileKey, setManualFileKey] = useState(0);
  const [reloadKey, setReloadKey] = useState(0);
  const [previewCopy, setPreviewCopy] = useState<{ assetId: string; text: string } | null>(null);

  useEffect(() => {
    let mounted = true;

    async function loadAssets() {
      setLoading(true);
      setMessage(null);
      try {
        const campaigns = await listCampaigns();
        setCampaigns(campaigns);
        setManualCampaignId((prev) => prev || campaigns[0]?.campaign_id || "");
        const settled = await Promise.allSettled(
          campaigns.map(async (campaign): Promise<AssetRow[]> => {
            const [bundle, validations] = await Promise.all([
              getCampaignBundle(campaign.campaign_id),
              listValidationResults(campaign.campaign_id),
            ]);
            const scoreMap = new Map(validations.map((item) => [item.asset_id, item.score]));
            const rows: AssetRow[] = [];

            for (const item of bundle.image_assets) {
              rows.push({
                assetId: item.asset_id,
                campaignId: campaign.campaign_id,
                campaignName: campaign.brief.campaign_name,
                type: "image",
                score: typeof item.score === "number" ? item.score : scoreMap.get(item.asset_id) ?? null,
                status: campaign.status,
                url: item.url,
                text: null,
              });
            }

            for (const item of bundle.video_assets) {
              rows.push({
                assetId: item.asset_id,
                campaignId: campaign.campaign_id,
                campaignName: campaign.brief.campaign_name,
                type: "video",
                score: typeof item.score === "number" ? item.score : scoreMap.get(item.asset_id) ?? null,
                status: campaign.status,
                url: item.url,
                text: null,
              });
            }

            for (const item of bundle.copy_assets) {
              rows.push({
                assetId: item.variant_id,
                campaignId: campaign.campaign_id,
                campaignName: campaign.brief.campaign_name,
                type: "copy",
                score: scoreMap.get(item.variant_id) ?? null,
                status: campaign.status,
                url: null,
                text: item.text,
              });
            }

            return rows;
          }),
        );

        const aggregated: AssetRow[] = settled.flatMap((item) => (item.status === "fulfilled" ? item.value : []));
        if (settled.some((item) => item.status === "rejected")) {
          setMessage(t("assets.fallback"));
        }

        if (!mounted) return;
        setRows(aggregated);
      } catch {
        if (!mounted) return;
        setRows([]);
        setMessage(t("assets.fallback"));
      } finally {
        if (mounted) setLoading(false);
      }
    }

    loadAssets();
    return () => {
      mounted = false;
    };
  }, [t, reloadKey]);

  async function handleManualUpload() {
    if (!manualCampaignId || !manualFile) return;
    try {
      await uploadManualAsset({ campaignId: manualCampaignId, assetType: manualType, file: manualFile, prompt: manualPrompt });
      setManualPrompt("");
      setManualFile(null);
      setManualFileKey((prev) => prev + 1);
      setMessage(t("assets.manualUploadSuccess"));
      setReloadKey((prev) => prev + 1);
    } catch {
      setMessage(t("assets.manualUploadFailed"));
    }
  }

  function applyAssetFilters() {
    setQuery(queryDraft);
    setTypeFilter(typeDraft);
    setValidationFilter(validationDraft);
  }

  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase();

    return rows.filter((item) => {
      if (typeFilter && item.type !== typeFilter) return false;
      if (validationFilter === "passed" && (item.score ?? 0) < 0.7) return false;
      if (validationFilter === "failed" && (item.score === null || item.score >= 0.7)) return false;
      if (!normalized) return true;

      return (
        item.assetId.toLowerCase().includes(normalized)
        || item.campaignName.toLowerCase().includes(normalized)
        || item.campaignId.toLowerCase().includes(normalized)
      );
    });
  }, [rows, query, typeFilter, validationFilter]);

  const metrics = useMemo(() => {
    const total = filtered.length;
    const passed = filtered.filter((item) => (item.score ?? 0) >= 0.7).length;
    const failed = filtered.filter((item) => item.score !== null && item.score < 0.7).length;
    return { total, passed, failed };
  }, [filtered]);

  return (
    <section className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">{t("assets.title")}</h1>
        <p className="text-sm text-slate-500">{t("assets.subtitle")}</p>
      </header>

      {message ? <p className="rounded-xl bg-amber-50 px-3 py-2 text-sm text-amber-700">{message}</p> : null}

      <div className="space-y-3 rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
        <h2 className="text-sm font-semibold">{t("assets.manualUploadTitle")}</h2>
        <div className="grid gap-3 md:grid-cols-[1fr_1fr_1.4fr_1.2fr_auto]">
          <select value={manualCampaignId} onChange={(event) => setManualCampaignId(event.target.value)} className="rounded-xl border border-slate-200 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950">
            {campaigns.map((campaign) => <option key={campaign.campaign_id} value={campaign.campaign_id}>{campaign.brief.campaign_name}</option>)}
          </select>
          <select value={manualType} onChange={(event) => setManualType(event.target.value as "image" | "video")} className="rounded-xl border border-slate-200 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950">
            <option value="image">{t("assets.type.image")}</option>
            <option value="video">{t("assets.type.video")}</option>
          </select>
          <input value={manualPrompt} onChange={(event) => setManualPrompt(event.target.value)} placeholder={t("assets.promptDescription")} className="rounded-xl border border-slate-200 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950" />
          <input key={manualFileKey} type="file" onChange={(event) => setManualFile(event.target.files?.[0] ?? null)} className="rounded-xl border border-slate-200 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950" />
          <button onClick={handleManualUpload} disabled={!manualCampaignId || !manualFile} className="rounded-xl bg-blue-600 px-3 py-2 text-sm font-medium text-white disabled:opacity-50">{t("assets.uploadAsset")}</button>
        </div>
      </div>

      <div className="grid gap-3 rounded-2xl border border-slate-200 bg-white p-4 md:grid-cols-[1fr_1fr_1fr_auto] dark:border-slate-800 dark:bg-slate-900">
        <input
          value={queryDraft}
          onChange={(event) => setQueryDraft(event.target.value)}
          placeholder={t("assets.searchPlaceholder")}
          aria-label={t("assets.searchPlaceholder")}
          className="rounded-xl border border-slate-200 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
        />
        <select
          value={typeDraft}
          onChange={(event) => setTypeDraft(event.target.value as "" | AssetType)}
          className="rounded-xl border border-slate-200 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
        >
          <option value="">{t("assets.allTypes")}</option>
          <option value="image">{t("assets.type.image")}</option>
          <option value="video">{t("assets.type.video")}</option>
          <option value="copy">{t("assets.type.copy")}</option>
        </select>
        <select
          value={validationDraft}
          onChange={(event) => setValidationDraft(event.target.value as "" | "passed" | "failed")}
          className="rounded-xl border border-slate-200 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
        >
          <option value="">{t("assets.allValidation")}</option>
          <option value="passed">{t("assets.validation.passed")}</option>
          <option value="failed">{t("assets.validation.failed")}</option>
        </select>
        <button onClick={applyAssetFilters} className="rounded-xl bg-slate-900 px-3 py-2 text-sm font-medium text-white dark:bg-slate-700">{t("common.apply")}</button>
      </div>

      <div className="grid gap-4 rounded-2xl border border-slate-200 bg-white p-4 md:grid-cols-3 dark:border-slate-800 dark:bg-slate-900">
        <Metric title={t("assets.metric.total")} value={metrics.total} tone="text-blue-600" />
        <Metric title={t("assets.metric.passed")} value={metrics.passed} tone="text-emerald-500" />
        <Metric title={t("assets.metric.failed")} value={metrics.failed} tone="text-rose-500" />
      </div>

      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <table className="min-w-full text-left text-sm">
          <thead className="border-b border-slate-200 bg-slate-50 text-slate-500 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-400">
            <tr>
              <th className="px-4 py-3">{t("assets.table.asset")}</th>
              <th className="px-4 py-3">{t("assets.table.campaign")}</th>
              <th className="px-4 py-3">{t("assets.table.type")}</th>
              <th className="px-4 py-3">{t("assets.table.score")}</th>
              <th className="px-4 py-3">{t("assets.table.status")}</th>
              <th className="px-4 py-3">{t("assets.table.action")}</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td className="px-4 py-6 text-center text-slate-500" colSpan={6}>{t("assets.loading")}</td>
              </tr>
            ) : filtered.length === 0 ? (
              <tr>
                <td className="px-4 py-6 text-center text-slate-500" colSpan={6}>{t("assets.empty")}</td>
              </tr>
            ) : filtered.map((item) => (
              <tr key={`${item.campaignId}-${item.assetId}`} className="border-b border-slate-200/70 last:border-none dark:border-slate-800">
                <td className="px-4 py-3 font-medium">{item.assetId}</td>
                <td className="px-4 py-3">{item.campaignName}</td>
                <td className="px-4 py-3">{typeLabel(item.type, t)}</td>
                <td className="px-4 py-3">{item.score === null ? t("common.notAvailable") : `${Math.round(item.score * 100)}%`}</td>
                <td className="px-4 py-3">
                  <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${statusClasses(item.score)}`}>
                    {validationLabel(item.score, t)}
                  </span>
                </td>
                <td className="px-4 py-3">
                  {item.type === "copy" ? (
                    item.text ? (
                      <button
                        onClick={() => setPreviewCopy({ assetId: item.assetId, text: item.text ?? "" })}
                        className="text-xs font-medium text-blue-600 hover:underline"
                      >
                        {t("assets.previewCopy")}
                      </button>
                    ) : (
                      <span className="text-xs text-slate-500">{t("common.notAvailable")}</span>
                    )
                  ) : item.url ? (
                    <a href={item.url} target="_blank" rel="noreferrer" className="text-xs font-medium text-blue-600 hover:underline">
                      {t("assets.openAsset")}
                    </a>
                  ) : (
                    <span className="text-xs text-slate-500">{t("common.notAvailable")}</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {previewCopy ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-2xl rounded-2xl bg-white p-4 shadow-xl dark:bg-slate-900">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-semibold">{t("assets.copyContent")} · {previewCopy.assetId}</h3>
              <button
                onClick={() => setPreviewCopy(null)}
                className="rounded-lg border border-slate-300 px-2.5 py-1.5 text-xs font-medium dark:border-slate-700"
              >
                {t("assets.closePreview")}
              </button>
            </div>
            <p className="mt-3 whitespace-pre-wrap rounded-xl border border-slate-200 p-3 text-sm dark:border-slate-700 dark:bg-slate-950">
              {previewCopy.text}
            </p>
          </div>
        </div>
      ) : null}
    </section>
  );
}

function Metric({ title, value, tone }: { title: string; value: number; tone: string }) {
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

function validationLabel(score: number | null, t: ReturnType<typeof useI18n>["t"]) {
  if (score === null) return t("common.notAvailable");
  if (score >= 0.7) return t("assets.validation.passed");
  return t("assets.validation.failed");
}

function statusClasses(score: number | null) {
  if (score === null) return "bg-slate-100 text-slate-700";
  if (score >= 0.7) return "bg-emerald-100 text-emerald-700";
  return "bg-rose-100 text-rose-700";
}
