import type { GenerationSourceProvenance } from "@/lib/api/campaigns";
import { provenanceText, safeExternalUrl } from "@/lib/campaign-diagnostics";

export function ProvenanceList({ sources }: { sources: GenerationSourceProvenance[] }) {
  return (
    <ul className="flex flex-wrap gap-2 text-xs text-slate-500">
      {sources.map((source) => {
        const url = safeExternalUrl(source.url);
        return (
          <li key={`${source.source_type}-${source.source_id}`} className="rounded-full bg-slate-100 px-2 py-1 dark:bg-slate-800">
            <span>{provenanceText(source)}</span>
            {url ? <a className="ml-1 underline" href={url} target="_blank" rel="noreferrer">{url}</a> : null}
          </li>
        );
      })}
    </ul>
  );
}
