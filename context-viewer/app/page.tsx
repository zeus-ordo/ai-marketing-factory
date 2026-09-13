"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

type Campaign = { campaign_id: string; campaign_name: string; status: string; created_at: string };
type ContextRow = { campaign_id: string; campaign_name: string; generation_context_id: string; run_id: string; created_at: string; activity_type?: string | null; status?: string | null; context_item_count: number; payload_count: number };
type Payload = { prompt?: string; context_json?: unknown; task_type?: string; model?: string };
type Detail = { generation_context_id: string; campaign_id: string; run_id: string; created_at: string; internal_token_count: number; external_token_count: number; internal_ratio: number; external_ratio: number; external_source_urls_json: unknown; external_search_status: string; external_search_error?: string | null; task_id?: string | null; selected_reference_ids_json: unknown; matched_folder_names_json: unknown; items: unknown[]; payloads: Payload[] };

const statuses = ["", "pending", "running", "completed", "failed"];
const activityTypes = ["", "copywriting", "image_generation", "video_generation", "chat"];

function humanize(value?: string | null) {
  if (!value) return "Uncategorized";
  return value.replace(/[_-]+/g, " ").replace(/\b\w/g, character => character.toUpperCase());
}

function formatDate(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : new Intl.DateTimeFormat("en", { dateStyle: "medium", timeStyle: "short" }).format(date);
}

function jsonText(value: unknown) { return JSON.stringify(value, null, 2); }

export default function HomePage() {
  const router = useRouter();
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

  async function loadCampaigns() {
    setCampaignError("");
    try { const response = await request(`/api/campaigns?search=${encodeURIComponent(campaignSearch)}`); setCampaigns(await response.json()); }
    catch { setCampaignError("We could not load campaigns. Try again."); }
  }

  async function loadContexts(overrides: Partial<{ campaign: string; context: string; run: string; activityType: string; status: string; from: string; to: string }> = {}) {
    setLoading(true); setError("");
    try {
      const params = new URLSearchParams({ limit: "100" });
      if (overrides.campaign ?? campaign) params.set("campaign_id", overrides.campaign ?? campaign);
      if (overrides.context ?? context) params.set("generation_context_id", overrides.context ?? context);
      if (overrides.run ?? run) params.set("run_id", overrides.run ?? run);
      if (overrides.activityType ?? activityType) params.set("activity_type", overrides.activityType ?? activityType);
      if (overrides.status ?? status) params.set("status", overrides.status ?? status);
      if (overrides.from ?? from) params.set("from", overrides.from ?? from);
      if (overrides.to ?? to) params.set("to", overrides.to ?? to);
      const response = await request(`/api/contexts?${params}`); setRows(await response.json());
    } catch { setError("We could not load AI activity. Try again."); }
    finally { setLoading(false); }
  }

  useEffect(() => { loadCampaigns().catch(() => undefined); loadContexts(); }, []);

  async function selectContext(id: string) {
    setActionError("");
    try { const response = await request(`/api/contexts/${encodeURIComponent(id)}`); setSelected(await response.json()); }
    catch { setError("We could not open this activity. Try again."); }
  }

  function clearFilters() {
    setCampaignSearch(""); setCampaign(""); setFrom(""); setTo(""); setActivityType(""); setStatus(""); setContext(""); setRun("");
    loadContexts({ campaign: "", from: "", to: "", activityType: "", status: "", context: "", run: "" });
  }

  function filterUrl() {
    const params = new URLSearchParams();
    for (const [key, value] of [["campaign_id", campaign], ["from", from], ["to", to], ["activity_type", activityType], ["status", status]] as const) if (value) params.set(key, value);
    return `/?${params}`;
  }

  async function copy(value: string, label: string) {
    setActionError("");
    try { await navigator.clipboard.writeText(value); }
    catch { setActionError(`Could not copy ${label}. Select the text and copy it manually.`); }
  }

  function download(name: string, value: string, type: string, label: string) {
    setActionError("");
    try { const link = document.createElement("a"); link.href = URL.createObjectURL(new Blob([value], { type })); link.download = name; link.click(); URL.revokeObjectURL(link.href); }
    catch { setActionError(`Could not download ${label}. Please try again.`); }
  }

  const selectedRow = selected && rows.find(row => row.generation_context_id === selected.generation_context_id);
  const prompt = selected?.payloads.map(payload => payload.prompt ?? "").join("\n\n") ?? "";
  const workerContext = selected ? jsonText(selected.payloads.map(payload => payload.context_json ?? {})) : "";
  const assembledContext = selected ? jsonText(selected.items) : "";
  const rawJson = selected ? jsonText(selected) : "";

  return <main className="shell">
    <header className="topbar"><div><p className="eyebrow">ADMINISTRATOR TOOL</p><h1>LLM Context Viewer</h1><p className="subtitle">Review what AI activity happened across your campaigns.</p></div><button className="button secondary" onClick={async () => { await fetch("/api/logout", { method: "POST" }); router.push("/login"); }}>Sign out</button></header>
    <section className="intro"><div><span className="kicker">Activity workbench</span><h2>AI activity</h2><p>Find a campaign run, check its status, and open the supporting context.</p></div><div className="activity-count" aria-label={`${rows.length} activity results`}><strong>{rows.length}</strong><span>results</span></div></section>
    <section className="panel filters" aria-labelledby="filter-heading"><div className="section-heading"><div><h2 id="filter-heading">Find activity</h2><p>Use the filters below to narrow the activity list.</p></div><button className="button text-button" onClick={clearFilters}>Clear filters</button></div><div className="filter-grid">
      <label className="field wide">Campaign<div className="search-control"><input list="campaign-options" placeholder="Search campaigns" value={campaignSearch} onChange={event => { setCampaignSearch(event.target.value); setCampaign(event.target.value); }} /><button className="button secondary" onClick={() => loadCampaigns()}>Search</button></div><datalist id="campaign-options">{campaigns.map(item => <option key={item.campaign_id} value={item.campaign_id}>{item.campaign_name}</option>)}</datalist></label>
      <label className="field"><span>Date</span><input type="date" aria-label="Date from" value={from} onChange={event => setFrom(event.target.value)} /><span className="date-separator">to</span><input type="date" aria-label="Date to" value={to} onChange={event => setTo(event.target.value)} /></label>
      <label className="field">Content type<select value={activityType} onChange={event => setActivityType(event.target.value)}>{activityTypes.map(item => <option key={item} value={item}>{item ? humanize(item) : "All content types"}</option>)}</select></label>
      <label className="field">Status<select value={status} onChange={event => setStatus(event.target.value)}>{statuses.map(item => <option key={item} value={item}>{item ? humanize(item) : "All statuses"}</option>)}</select></label>
    </div>{campaignError && <p className="field-error" role="alert">{campaignError}</p>}<details className="technical"><summary>Technical details</summary><div className="technical-grid"><label className="field">Generation context ID<input value={context} onChange={event => setContext(event.target.value)} /></label><label className="field">Run ID<input value={run} onChange={event => setRun(event.target.value)} /></label></div></details><div className="filter-actions"><button className="button primary" onClick={() => loadContexts()}>Apply filters</button></div></section>
    {error && <div className="notice error" role="alert">{error}</div>}
    <div className="content-grid"><section className="panel activity-panel" aria-labelledby="activity-list-heading"><div className="section-heading"><div><h2 id="activity-list-heading">Recent activity</h2><p>{loading ? "Loading activity..." : "Select an activity to see its context."}</p></div></div>{loading ? <div className="empty-state"><span className="spinner" aria-hidden="true" /><p>Loading AI activity...</p></div> : rows.length === 0 ? <div className="empty-state"><div className="empty-icon" aria-hidden="true">--</div><h3>No AI activity found</h3><p>Try clearing a filter or choosing a different date range.</p></div> : <div className="activity-list">{rows.map(row => <article className={`activity-card ${selected?.generation_context_id === row.generation_context_id ? "selected" : ""}`} key={row.generation_context_id}><div className="card-main"><div className="card-title"><span className="activity-dot" aria-hidden="true" /><h3>{humanize(row.activity_type)}</h3><span className={`status status-${row.status ?? "unknown"}`}>{humanize(row.status)}</span></div><p className="campaign-name">{row.campaign_name}<span className="technical-reference">{row.campaign_id}</span></p><p className="timestamp">{formatDate(row.created_at)}</p></div><dl className="card-stats"><div><dt>References</dt><dd>{row.context_item_count}</dd></div><div><dt>Outputs</dt><dd>{row.payload_count}</dd></div></dl><button className="button secondary open-button" onClick={() => selectContext(row.generation_context_id)}>View details<span aria-hidden="true"> &rarr;</span></button></article>)}</div>}</section>
      <section className="panel detail-panel" aria-labelledby="detail-heading">{selected ? <><div className="detail-header"><a className="back-link" href={filterUrl()}>Back to activity list</a><div className="detail-heading-row"><div><p className="eyebrow">Activity record</p><h2 id="detail-heading">{selectedRow?.campaign_name ?? selected.campaign_id}</h2><p className="detail-context">{humanize(selectedRow?.activity_type)} &middot; {formatDate(selected.created_at)}</p></div><span className={`status status-${selectedRow?.status ?? "unknown"}`}>{humanize(selectedRow?.status)}</span></div></div><div className="summary-grid"><SummaryCard label="Requested output" value={`${selected.payloads.length} instruction${selected.payloads.length === 1 ? "" : "s"}`} /><SummaryCard label="Information used" value={`${selected.items.length} source${selected.items.length === 1 ? "" : "s"}`} /><SummaryCard label="Generated result" value={`${selected.payloads.length} result${selected.payloads.length === 1 ? "" : "s"}`} /><SummaryCard label="Model response" value={humanize(selectedRow?.status)} /></div>{actionError && <p className="notice error" role="alert">{actionError}</p>}<div className="detail-content"><DetailPanel title="What we asked the AI to do" description="The complete instruction sent for this activity." text={prompt} copyLabel="instruction" onCopy={() => copy(prompt, "instruction")} onText={() => download(`${selected.generation_context_id}-prompts.txt`, prompt, "text/plain", "instruction")} onJson={() => download(`${selected.generation_context_id}-prompts.json`, jsonText(selected.payloads), "application/json", "instruction JSON")} /><section className="detail-card source-card"><div className="detail-card-heading"><div><h3>Information given to the AI</h3><p>Sources and context included with the instruction.</p></div><div className="detail-actions"><button onClick={() => copy(workerContext, "information")}>Copy information</button><button onClick={() => download(`${selected.generation_context_id}-worker-context.txt`, workerContext, "text/plain", "information")}>Download text</button><button onClick={() => download(`${selected.generation_context_id}-worker-context.json`, workerContext, "application/json", "information JSON")}>Download JSON</button></div></div><ul className="source-list">{selected.items.map((item, index) => <li key={index}><strong>Reference {index + 1}</strong><span>{typeof item === "object" && item !== null ? Object.keys(item as object).slice(0, 3).join(", ") || "Context item" : String(item)}</span></li>)}</ul><details><summary>View all information</summary><pre>{assembledContext}</pre></details></section><DetailPanel title="What the AI returned" description="Review the generated result count and the complete returned payload." text={jsonText(selected.payloads)} copyLabel="result" onCopy={() => copy(jsonText(selected.payloads), "result")} onText={() => download(`${selected.generation_context_id}-results.txt`, jsonText(selected.payloads), "text/plain", "result")} onJson={() => download(`${selected.generation_context_id}-results.json`, jsonText(selected.payloads), "application/json", "result JSON")} /><details className="technical detail-technical"><summary>Technical details</summary><dl className="metadata-grid"><Meta label="Generation context ID" value={selected.generation_context_id} /><Meta label="Run ID" value={selected.run_id} /><Meta label="Task ID" value={selected.task_id ?? "Not available"} /><Meta label="Model" value={selected.payloads.map(payload => payload.model).filter(Boolean).join(", ") || "Not available"} /><Meta label="Internal tokens" value={String(selected.internal_token_count)} /><Meta label="External tokens" value={String(selected.external_token_count)} /><Meta label="Internal ratio" value={String(selected.internal_ratio)} /><Meta label="External ratio" value={String(selected.external_ratio)} /><Meta label="Search status" value={selected.external_search_status} /></dl><DetailPanel title="Raw JSON" text={rawJson} copyLabel="raw JSON" onCopy={() => copy(rawJson, "raw JSON")} onText={() => download(`${selected.generation_context_id}-metadata.txt`, rawJson, "text/plain", "raw JSON")} onJson={() => download(`${selected.generation_context_id}-metadata.json`, rawJson, "application/json", "raw JSON")} /></details></div></> : <><h2 id="detail-heading">Next step</h2><div className="next-step"><div className="next-icon" aria-hidden="true">+</div><h3>Select an activity</h3><p>Choose an activity from the list to inspect its prompts and assembled context.</p></div></>}</section></div>
  </main>;
}

function SummaryCard({ label, value }: { label: string; value: string }) { return <div className="summary-card"><span>{label}</span><strong>{value}</strong></div>; }
function Meta({ label, value }: { label: string; value: string }) { return <div><dt>{label}</dt><dd>{value}</dd></div>; }
function DetailPanel({ title, description = "Generation context metadata", text, copyLabel, onCopy, onText, onJson }: { title: string; description?: string; text: string; copyLabel: string; onCopy: () => void; onText: () => void; onJson: () => void }) {
  return <article className="detail-card"><div className="detail-card-heading"><div><h3>{title}</h3><p>{description}</p></div><div className="detail-actions"><button onClick={onCopy}>{copyLabel === "instruction" ? "Copy instruction" : `Copy ${copyLabel}`}</button><button onClick={onText}>Download text</button><button onClick={onJson}>Download JSON</button></div></div><pre>{text}</pre></article>;
}
