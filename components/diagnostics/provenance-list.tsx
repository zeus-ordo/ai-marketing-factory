import type { GenerationSourceProvenance } from "@/lib/api/campaigns";
import { safeExternalUrl } from "@/lib/campaign-diagnostics";
import { useI18n } from "@/lib/i18n/context";

export function ProvenanceList({ sources }: { sources: GenerationSourceProvenance[] }) {
  const { t } = useI18n();
  return (
    <ul className="flex flex-wrap gap-2 text-xs text-slate-500">
      {sources.map((source) => {
        const url = safeExternalUrl(source.url);
        return (
          <li key={`${source.source_type}-${source.source_id}`} className="rounded-full bg-slate-100 px-2 py-1 dark:bg-slate-800">
            <span>{[sourceTypeLabel(source.source_type, t), source.label, source.folder].filter(Boolean).join(" · ")}</span>
            {url ? <a className="ml-1 underline" href={url} target="_blank" rel="noreferrer">{url}</a> : null}
          </li>
        );
      })}
    </ul>
  );
}

function sourceTypeLabel(sourceType: string, t: ReturnType<typeof useI18n>["t"]) {
  if (sourceType === "campaign_reference") return t("review.diagnostics.sourceTypes.campaignReference");
  if (sourceType === "immediate_upload") return t("review.diagnostics.sourceTypes.immediateUpload");
  if (sourceType === "user_selected") return t("review.diagnostics.sourceTypes.userSelected");
  if (sourceType === "industry_matched") return t("review.diagnostics.sourceTypes.industryMatched");
  if (sourceType === "external_web") return t("review.diagnostics.sourceTypes.externalWeb");
  return t("common.notAvailable");
}
