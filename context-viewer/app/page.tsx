"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { formatDate } from "../lib/format.ts";
import { referenceAuditFromPayloads, removeBinaryData, type ReferenceAudit } from "../lib/reference-audit.ts";

type Campaign = { campaign_id: string; campaign_name: string; status: string; created_at: string };
type ContextRow = { campaign_id: string; campaign_name: string; generation_context_id: string; run_id: string; created_at: string; activity_type?: string | null; status?: string | null; context_item_count: number; payload_count: number; output_count: number };
type Payload = { prompt?: string; context_json?: unknown; task_type?: string; model?: string };
type Output = { asset_id?: string; task_id?: string; asset_type?: string; url?: string; metadata_json?: unknown; validation_status?: string; created_at?: string };
type Detail = { generation_context_id: string; campaign_id: string; run_id: string; created_at: string; internal_token_count: number; external_token_count: number; internal_ratio: number; external_ratio: number; external_source_urls_json: unknown; external_search_status: string; external_search_error?: string | null; task_id?: string | null; selected_reference_ids_json: unknown; matched_folder_names_json: unknown; items: unknown[]; payloads: Payload[]; outputs: Output[] };
type FilterValues = { campaign: string; context: string; run: string; activityType: string; status: string; from: string; to: string };
type ContextItem = { source_type?: unknown; source_id?: unknown; label?: unknown; file_name?: unknown; text?: unknown; query?: unknown; metadata?: unknown; [key: string]: unknown };

const statuses = [
  { value: "", label: "All statuses" },
  { value: "pending", label: "Waiting" },
  { value: "planned", label: "Ready" },
  { value: "running", label: "In progress" },
  { value: "validating", label: "Validating" },
  { value: "passed", label: "Passed" },
  { value: "completed", label: "Completed" },
  { value: "failed", label: "Failed" },
  { value: "review_pending", label: "Needs review" },
  { value: "blocked", label: "Blocked" },
  { value: "retrying", label: "Retrying" },
];
const activityTypes = [
  { value: "", label: "All content types" },
  { value: "copywriting", label: "Copywriting" },
  { value: "image_generation", label: "Image generation" },
  { value: "video_generation", label: "Video generation" },
  { value: "ads_strategy", label: "Ads strategy" },
];

function humanize(value?: string | null) { return value ? value.replace(/[_-]+/g, " ").replace(/\b\w/g, character => character.toUpperCase()) : "Uncategorized"; }
function jsonText(value: unknown) { return JSON.stringify(removeBinaryData(value), null, 2); }
function contextItemSummary(item: unknown, index: number) {
  const record = item && typeof item === "object" ? item as ContextItem : {};
  const metadata = record.metadata && typeof record.metadata === "object" ? record.metadata as Record<string, unknown> : {};
  const value = (...keys: string[]) => keys.map(key => record[key] ?? metadata[key]).find(candidate => candidate !== undefined && candidate !== null && String(candidate).trim()) as string | undefined;
  return { label: value("label", "file_name", "name") || `Reference ${index + 1}`, folder: value("folder", "folder_name") || "Folder not recorded", sourceType: humanize(value("source_type") || "Unknown source"), text: value("text", "query", "summary", "description") || "No text or query recorded" };
}
function outputSummary(outputs: Output[]) {
  if (!outputs.length) return "No generated output was persisted for this activity.";
  return outputs.map((output, index) => {
    const metadata = output.metadata_json && typeof output.metadata_json === "object" ? output.metadata_json as Record<string, unknown> : {};
    const text = [metadata.text, metadata.content, metadata.copy, metadata.description].find(value => typeof value === "string" && value.trim()) as string | undefined;
    const name = typeof metadata.asset_name === "string" && metadata.asset_name.trim() ? metadata.asset_name : `Output ${index + 1}`;
    const lines = [`${name} (${humanize(output.asset_type)})`];
    if (text) lines.push(text);
    if (output.url) lines.push(`Result: ${output.url}`);
    if (output.validation_status) lines.push(`Review status: ${humanize(output.validation_status)}`);
    return lines.join("\n");
  }).join("\n\n");
}
function filtersFromUrl(searchParams: { get(name: string): string | null }): FilterValues {
  return { campaign: searchParams.get("campaign_id") ?? "", context: searchParams.get("generation_context_id") ?? "", run: searchParams.get("run_id") ?? "", activityType: searchParams.get("activity_type") ?? "", status: searchParams.get("status") ?? "", from: searchParams.get("from") ?? "", to: searchParams.get("to") ?? "" };
}

function campaignFilter(value: string): [string, string] | null { return value ? ["campaign_id", value] : null; }

function ViewerPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [campaignSearch, setCampaignSearch] = useState("");
  const [campaign, setCampaign] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [activityType, setActivityType] = useState("");
  const [status, setStatus] = useState("");
  const [context, setContext] = useState("");
  const [run, setRun] = useState("");
  const [rows, setRows] = useState<ContextRow[]>([]);
  const [selected, setSelected] = useState<Detail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [campaignError, setCampaignError] = useState("");
  const [actionError, setActionError] = useState("");

  async function request(path: string, init?: RequestInit) {
    const response = await fetch(path, init);
    if (response.status === 401) { router.push("/login"); throw new Error("Unauthorized"); }
    if (!response.ok) throw new Error("Request failed");
    return response;
  }
  async function loadCampaigns() { setCampaignError(""); try { setCampaigns(await (await request(`/api/campaigns?search=${encodeURIComponent(campaignSearch)}`)).json()); } catch { setCampaignError("We could not load campaigns. Try again."); } }
  async function loadContexts(overrides: Partial<FilterValues> = {}) {
    setLoading(true); setError("");
    try {
      const params = new URLSearchParams({ limit: "100" });
      const values = { campaign, context, run, activityType, status, from, to, ...overrides };
      const selectedCampaign = campaignFilter(values.campaign);
      if (selectedCampaign) params.set(selectedCampaign[0], selectedCampaign[1]);
      if (values.context) params.set("generation_context_id", values.context);
      if (values.run) params.set("run_id", values.run);
      if (values.activityType) params.set("activity_type", values.activityType);
      if (values.status) params.set("status", values.status);
      if (values.from) params.set("from", values.from);
      if (values.to) params.set("to", values.to);
      setRows(await (await request(`/api/contexts?${params}`)).json());
    } catch { setError("We could not load AI activity. Try again."); } finally { setLoading(false); }
  }
  useEffect(() => {
    const restoredFilters = filtersFromUrl(searchParams);
    setCampaignSearch(restoredFilters.campaign); setCampaign(restoredFilters.campaign); setContext(restoredFilters.context); setRun(restoredFilters.run); setActivityType(restoredFilters.activityType); setStatus(restoredFilters.status); setFrom(restoredFilters.from); setTo(restoredFilters.to);
    loadCampaigns().catch(() => undefined); loadContexts(restoredFilters);
  }, [searchParams]);
  useEffect(() => {
    if (selected && !rows.some(row => row.generation_context_id === selected.generation_context_id)) setSelected(null);
  }, [rows, selected]);
  async function selectContext(id: string) { setActionError(""); try { setSelected(await (await request(`/api/contexts/${encodeURIComponent(id)}`)).json()); } catch { setError("We could not open this activity. Try again."); } }
  function clearFilters() { const empty: FilterValues = { campaign: "", context: "", run: "", activityType: "", status: "", from: "", to: "" }; setCampaignSearch(""); setCampaign(""); setFrom(""); setTo(""); setActivityType(""); setStatus(""); setContext(""); setRun(""); loadContexts(empty); }
  function filterUrl() { const params = new URLSearchParams(); for (const [key, value] of [["campaign_id", campaign], ["from", from], ["to", to], ["activity_type", activityType], ["status", status]] as const) if (value) params.set(key, value); return `/?${params}`; }
  async function copy(value: string, label: string) { setActionError(""); try { await navigator.clipboard.writeText(value); } catch { setActionError(`Could not copy ${label}. Select the text and copy it manually.`); } }
  function download(name: string, value: string, type: string, label: string) { setActionError(""); try { const link = document.createElement("a"); link.href = URL.createObjectURL(new Blob([value], { type })); link.download = name; link.click(); URL.revokeObjectURL(link.href); } catch { setActionError(`Could not download ${label}. Please try again.`); } }

  const selectedRow = selected && rows.find(row => row.generation_context_id === selected.generation_context_id);
  const prompt = selected?.payloads.length ? selected.payloads.map(payload => payload.prompt ?? "").join("\n\n") : "The exact instruction was not captured for this historical activity. Exact prompt capture was added later, so this record cannot show what was sent.";
  const workerContext = selected ? jsonText(selected.payloads.map(payload => removeBinaryData(payload.context_json ?? {}))) : "";
  const assembledContext = selected ? jsonText(removeBinaryData(selected.items)) : "";
  const rawJson = selected ? jsonText(removeBinaryData(selected)) : "";
  const outputs = selected ? selected.outputs : [];
  const resultText = outputs.length ? outputSummary(outputs) : `No generated output was persisted for this activity.\nPersisted outcome: ${humanize(selectedRow?.status ?? "unknown")}.`;

  return <main className="shell">
    <header className="topbar"><div><p className="eyebrow">ADMINISTRATOR TOOL</p><h1>LLM Context Viewer</h1><p className="subtitle">Review what AI activity happened across your campaigns.</p></div><button className="button secondary" onClick={async () => { await fetch("/api/logout", { method: "POST" }); router.push("/login"); }}>Sign out</button></header>
    <section className="intro"><div><span className="kicker">Activity workbench</span><h2>AI activity</h2><p>Find a campaign run, check its status, and open the supporting context.</p></div><div className="activity-count" aria-label={`${rows.length} activity results`}><strong>{rows.length}</strong><span>results</span></div></section>
    <section className="panel filters" aria-labelledby="filter-heading"><div className="section-heading"><div><h2 id="filter-heading">Find activity</h2><p>Use the filters below to narrow the activity list.</p></div><button className="button text-button" onClick={clearFilters}>Clear filters</button></div><div className="filter-grid">
      <label className="field wide">Campaign<div className="search-control"><input list="campaign-options" placeholder="Search campaigns" value={campaignSearch} onChange={event => { setCampaignSearch(event.target.value); setCampaign(event.target.value); }} /><button className="button secondary" onClick={() => loadCampaigns()}>Search</button></div><datalist id="campaign-options">{campaigns.map(item => <option key={item.campaign_id} value={item.campaign_name}>{item.campaign_id}</option>)}</datalist></label>
      <label className="field"><span>Date</span><input type="date" aria-label="Date from" value={from} onChange={event => setFrom(event.target.value)} /><span className="date-separator">to</span><input type="date" aria-label="Date to" value={to} onChange={event => setTo(event.target.value)} /></label>
      <label className="field">Content type<select value={activityType} onChange={event => setActivityType(event.target.value)}>{activityTypes.map(item => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
      <label className="field">Status<select value={status} onChange={event => setStatus(event.target.value)}>{statuses.map(item => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
    </div>{campaignError && <p className="field-error" role="alert">{campaignError}</p>}<details className="technical"><summary>Technical details</summary><div className="technical-grid"><label className="field">Generation context ID<input value={context} onChange={event => setContext(event.target.value)} /></label><label className="field">Run ID<input value={run} onChange={event => setRun(event.target.value)} /></label></div></details><div className="filter-actions"><button className="button primary" onClick={() => loadContexts()}>Apply filters</button></div></section>
    {error && <div className="notice error" role="alert">{error}</div>}
    <div className="content-grid"><ActivityList rows={rows} loading={loading} selected={selected} onSelect={selectContext} /><section className="panel detail-panel" aria-labelledby="detail-heading">{selected ? <><div className="detail-header"><a className="back-link" href={filterUrl()}>Back to activity list</a><div className="detail-heading-row"><div><p className="eyebrow">Activity record</p><h2 id="detail-heading">{selectedRow?.campaign_name ?? selected.campaign_id}</h2><p className="detail-context">{humanize(selectedRow?.activity_type)} &middot; {formatDate(selected.created_at)}</p></div><span className={`status status-${selectedRow?.status ?? "unknown"}`}>{humanize(selectedRow?.status)}</span></div></div><div className="summary-grid"><SummaryCard label="Requested output" value={`${selected.payloads.length} instruction${selected.payloads.length === 1 ? "" : "s"}`} /><SummaryCard label="Information used" value={`${selected.items.length} source${selected.items.length === 1 ? "" : "s"}`} /><SummaryCard label="Generated result" value={outputs.length ? `${outputs.length} persisted output${outputs.length === 1 ? "" : "s"}` : "No persisted output"} /><SummaryCard label="Model response" value={humanize(selectedRow?.status)} /></div>{actionError && <p className="notice error" role="alert">{actionError}</p>}<div className="detail-content"><DetailPanel title="What we asked the AI to do" description="The complete instruction sent for this activity." text={prompt} copyLabel="instruction" onCopy={() => copy(prompt, "instruction")} onText={() => download(`${selected.generation_context_id}-prompts.txt`, prompt, "text/plain", "instruction")} onJson={() => download(`${selected.generation_context_id}-prompts.json`, jsonText(selected.payloads), "application/json", "instruction JSON")} /><SourcePanel selected={selected} workerContext={workerContext} assembledContext={assembledContext} onCopy={copy} onDownload={download} /><DetailPanel title="What the AI returned" description="Persisted generated outputs are shown here when available; otherwise the activity outcome is stated plainly." text={resultText} copyLabel="result" onCopy={() => copy(resultText, "result")} onText={() => download(`${selected.generation_context_id}-results.txt`, resultText, "text/plain", "result")} onJson={() => download(`${selected.generation_context_id}-results.json`, resultText, "application/json", "result JSON")} /><details className="technical detail-technical"><summary>Technical details</summary><dl className="metadata-grid"><Meta label="Generation context ID" value={selected.generation_context_id} /><Meta label="Run ID" value={selected.run_id} /><Meta label="Task ID" value={selected.task_id ?? "Not available"} /><Meta label="Model" value={selected.payloads.map(payload => payload.model).filter(Boolean).join(", ") || "Not available"} /><Meta label="Internal tokens" value={String(selected.internal_token_count)} /><Meta label="External tokens" value={String(selected.external_token_count)} /><Meta label="Internal ratio" value={String(selected.internal_ratio)} /><Meta label="External ratio" value={String(selected.external_ratio)} /><Meta label="Search status" value={selected.external_search_status} /></dl><DetailPanel title="Raw JSON" text={rawJson} copyLabel="raw JSON" onCopy={() => copy(rawJson, "raw JSON")} onText={() => download(`${selected.generation_context_id}-metadata.txt`, rawJson, "text/plain", "raw JSON")} onJson={() => download(`${selected.generation_context_id}-metadata.json`, rawJson, "application/json", "raw JSON")} /></details></div></> : <><h2 id="detail-heading">Next step</h2><div className="next-step"><div className="next-icon" aria-hidden="true">+</div><h3>Select an activity</h3><p>Choose an activity from the list to inspect its prompts and assembled context.</p></div></>}</section></div>
  </main>;
}

function ActivityList({ rows, loading, selected, onSelect }: { rows: ContextRow[]; loading: boolean; selected: Detail | null; onSelect: (id: string) => void }) {
  return <section className="panel activity-panel" aria-labelledby="activity-list-heading">
    <div className="section-heading"><div><h2 id="activity-list-heading">Recent activity</h2><p>{loading ? "Loading activity..." : "Select an activity to see its context."}</p></div></div>
    {loading ? <div className="empty-state"><span className="spinner" aria-hidden="true" /><p>Loading AI activity...</p></div> : rows.length === 0 ? <div className="empty-state"><div className="empty-icon" aria-hidden="true">--</div><h3>No AI activity found</h3><p>Try clearing a filter or choosing a different date range.</p></div> : <div className="activity-list">{rows.map(row => <article className={`activity-card ${selected?.generation_context_id === row.generation_context_id ? "selected" : ""}`} key={row.generation_context_id}>
      <div className="card-main"><div className="card-title"><span className="activity-dot" aria-hidden="true" /><h3>{humanize(row.activity_type)}</h3><span className={`status status-${row.status ?? "unknown"}`}>{humanize(row.status)}</span></div><p className="campaign-name">{row.campaign_name}<span className="technical-reference">{row.campaign_id}</span></p><p className="timestamp">{formatDate(row.created_at)}</p></div>
      <dl className="card-stats"><div><dt>References</dt><dd>{row.context_item_count}</dd></div><div><dt>Outputs</dt><dd>{row.output_count}</dd></div></dl>
      <button className="button secondary open-button" onClick={() => onSelect(row.generation_context_id)}>View details<span aria-hidden="true"> &rarr;</span></button>
    </article>)}</div>}
  </section>;
}
function ReferenceSourcePanel({ selected, workerContext, assembledContext, audit, onCopy, onDownload }: { selected: Detail; workerContext: string; assembledContext: string; audit: ReferenceAudit | null; onCopy: (value: string, label: string) => void; onDownload: (name: string, value: string, type: string, label: string) => void }) { return <section className="detail-card source-card"><div className="detail-card-heading"><div><h3>References supplied</h3><p>References and context supplied with the instruction. {selected.items.length} source{selected.items.length === 1 ? "" : "s"} recorded.</p></div><div className="detail-actions"><button onClick={() => onCopy(workerContext, "information")}>Copy information</button><button onClick={() => onDownload(`${selected.generation_context_id}-worker-context.txt`, workerContext, "text/plain", "information")}>Download text</button><button onClick={() => onDownload(`${selected.generation_context_id}-worker-context.json`, workerContext, "application/json", "information JSON")}>Download JSON</button></div></div><ul className="source-list">{selected.items.map((item, index) => { const summary = contextItemSummary(item, index); return <li key={index}><strong>Reference: {summary.label}</strong><span>Folder: {summary.folder} &middot; Source type: {summary.sourceType}</span><span>{summary.text}</span></li>; })}</ul><ReferenceAuditPanel audit={audit} /><details><summary>Technical context — raw prompt and context remain available</summary><pre>{assembledContext}</pre></details></section>; }
function SourcePanel({ selected, workerContext, assembledContext, onCopy, onDownload }: { selected: Detail; workerContext: string; assembledContext: string; onCopy: (value: string, label: string) => void; onDownload: (name: string, value: string, type: string, label: string) => void }) { const referenceAudit = referenceAuditFromPayloads(selected.payloads); return <ReferenceSourcePanel selected={selected} workerContext={workerContext} assembledContext={assembledContext} audit={referenceAudit} onCopy={onCopy} onDownload={onDownload} />; }
function ReferenceAuditPanel({ audit }: { audit: ReferenceAudit | null }) {
  if (!audit) return <div className="audit-panel"><strong>Reference attachment audit</strong><p>Audit unavailable for this activity</p></div>;
  const successful = audit.selectedCount === audit.attachedCount && audit.failures.length === 0;
  return <div className="audit-panel"><div className="audit-heading"><div><strong>Reference attachment audit</strong><p className={`status ${successful ? "status-completed" : "status-failed"}`}>{successful ? "Attached successfully" : "Attachment incomplete/failed"}</p></div><p>Selected: {audit.selectedCount}</p><p>Attached: {audit.attachedCount}</p><p>Multimodal: {audit.multimodal ? "Yes" : "No"}</p></div>{audit.references.length > 0 && <ul className="source-list">{audit.references.map((reference, index) => <li key={`${reference.referenceId}-${index}`}><strong>Reference ID: {reference.referenceId}</strong><span>File: {reference.fileName} &middot; MIME: {reference.mimeType}</span><span>Folder: {reference.folder} &middot; SHA-256: {reference.sha256}</span></li>)}</ul>}{audit.failures.length > 0 && <ul className="source-list">{audit.failures.map((failure, index) => <li key={`${failure.referenceId}-${index}`}><strong>Failed reference ID: {failure.referenceId}</strong><span>Category: {failure.category}</span></li>)}</ul>}</div>;
}
function SummaryCard({ label, value }: { label: string; value: string }) { return <div className="summary-card"><span>{label}</span><strong>{value}</strong></div>; }
function Meta({ label, value }: { label: string; value: string }) { return <div><dt>{label}</dt><dd>{value}</dd></div>; }
function DetailPanel({ title, description = "Generation context metadata", text, copyLabel, onCopy, onText, onJson }: { title: string; description?: string; text: string; copyLabel: string; onCopy: () => void; onText: () => void; onJson: () => void }) { const displayTitle = title === "What we asked the AI to do" ? "What we sent to the AI" : title; return <article className="detail-card"><div className="detail-card-heading"><div><h3>{displayTitle}</h3><p>{description}</p></div><div className="detail-actions"><button onClick={onCopy}>{copyLabel === "instruction" ? "Copy instruction" : `Copy ${copyLabel}`}</button><button onClick={onText}>Download text</button><button onClick={onJson}>Download JSON</button></div></div><pre>{text}</pre>{title === "What the AI returned" && <section className="next-step result-next-step" aria-label="Next step"><h3>Next step</h3><p>Use the persisted output above in your campaign workflow, or return to the activity list.</p><a className="back-link" href="#activity-list-heading">Review activity list</a></section>}</article>; }

export default function HomePage() { return <Suspense fallback={<main className="shell"><p>Loading activity...</p></main>}><ViewerPage /></Suspense>; }
