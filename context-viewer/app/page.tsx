"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

type Campaign = { campaign_id: string; status: string; created_at: string };
type ContextRow = { campaign_id: string; generation_context_id: string; run_id: string; created_at: string; context_item_count: number; payload_count: number };
type Detail = { generation_context_id: string; campaign_id: string; run_id: string; items: unknown[]; payloads: Array<{ prompt?: string; context_json?: unknown; task_type?: string; model?: string }> };

const panelStyle = { background: "white", borderRadius: 12, padding: 20 };

export default function HomePage() {
  const router = useRouter();
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [campaignSearch, setCampaignSearch] = useState("");
  const [campaign, setCampaign] = useState("");
  const [context, setContext] = useState("");
  const [run, setRun] = useState("");
  const [rows, setRows] = useState<ContextRow[]>([]);
  const [selected, setSelected] = useState<Detail | null>(null);

  async function request(path: string, init?: RequestInit) {
    const response = await fetch(path, init);
    if (response.status === 401) { router.push("/login"); throw new Error("Unauthorized"); }
    return response;
  }

  async function loadCampaigns() {
    const response = await request(`/api/campaigns?search=${encodeURIComponent(campaignSearch)}`);
    setCampaigns(await response.json());
  }

  async function loadContexts(selectedCampaign = campaign) {
    const params = new URLSearchParams({ limit: "100" });
    if (selectedCampaign) params.set("campaign_id", selectedCampaign);
    if (context) params.set("generation_context_id", context);
    if (run) params.set("run_id", run);
    const response = await request(`/api/contexts?${params}`);
    setRows(await response.json());
  }

  useEffect(() => { loadCampaigns().catch(() => undefined); loadContexts().catch(() => undefined); }, []);

  async function selectContext(id: string) {
    const response = await request(`/api/contexts/${encodeURIComponent(id)}`);
    setSelected(await response.json());
  }

  function payloadText() { return selected?.payloads.map(payload => payload.prompt ?? "").join("\n\n") ?? ""; }
  function workerContextText() { return JSON.stringify(selected?.payloads.map(payload => payload.context_json ?? {}) ?? [], null, 2); }
  function assembledContextText() { return JSON.stringify(selected?.items ?? [], null, 2); }
  function copy(value: string) { navigator.clipboard.writeText(value); }
  function download(name: string, value: string, type: string) { const link = document.createElement("a"); link.href = URL.createObjectURL(new Blob([value], { type })); link.download = name; link.click(); URL.revokeObjectURL(link.href); }

  return <main style={{ maxWidth: 1400, margin: "0 auto", padding: "24px 20px" }}>
    <header style={{ display: "flex", justifyContent: "space-between", alignItems: "start" }}><div><p style={{ color: "#5d6b7a", letterSpacing: 2 }}>ADMINISTRATOR TOOL</p><h1>LLM Context Viewer</h1></div><button onClick={async () => { await fetch("/api/logout", { method: "POST" }); router.push("/login"); }}>Sign out</button></header>
    <section style={{ ...panelStyle, marginBottom: 16 }}><h2>Campaigns</h2><div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}><input placeholder="Search campaign IDs" value={campaignSearch} onChange={e => setCampaignSearch(e.target.value)} /><button onClick={() => loadCampaigns().catch(() => undefined)}>Search</button></div><div style={{ display: "flex", gap: 8, overflowX: "auto", marginTop: 12 }}>{campaigns.map(item => <button key={item.campaign_id} onClick={() => { setCampaign(item.campaign_id); loadContexts(item.campaign_id).catch(() => undefined); }}>{item.campaign_id} ({item.status})</button>)}</div></section>
    <section style={{ ...panelStyle, marginBottom: 16 }}><h2>Filters</h2><div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}><input placeholder="Campaign ID" value={campaign} onChange={e => setCampaign(e.target.value)} /><input placeholder="Generation context ID" value={context} onChange={e => setContext(e.target.value)} /><input placeholder="Run ID" value={run} onChange={e => setRun(e.target.value)} /><button onClick={() => loadContexts().catch(() => undefined)}>Apply filters</button></div></section>
    <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) minmax(0, 1.5fr)", gap: 16 }}><section style={{ ...panelStyle, overflow: "auto" }}><h2>Generation contexts</h2><table style={{ width: "100%", textAlign: "left", minWidth: 600 }}><thead><tr><th>Campaign</th><th>Generation context</th><th>Run</th><th>Payloads</th></tr></thead><tbody>{rows.map(row => <tr key={row.generation_context_id} onClick={() => selectContext(row.generation_context_id)} style={{ cursor: "pointer" }}><td>{row.campaign_id}</td><td>{row.generation_context_id}</td><td>{row.run_id}</td><td>{row.payload_count}</td></tr>)}</tbody></table></section>
      <section style={{ ...panelStyle, minWidth: 0 }}><h2>{selected ? selected.generation_context_id : "Detail"}</h2>{selected ? <div style={{ display: "grid", gap: 16 }}><DetailPanel title="Prompts" text={payloadText()} onCopy={() => copy(payloadText())} onText={() => download(`${selected.generation_context_id}-prompts.txt`, payloadText(), "text/plain")} onJson={() => download(`${selected.generation_context_id}-prompts.json`, JSON.stringify(selected.payloads, null, 2), "application/json")} /><DetailPanel title="Persisted worker context payload" text={workerContextText()} onCopy={() => copy(workerContextText())} onText={() => download(`${selected.generation_context_id}-worker-context.txt`, workerContextText(), "text/plain")} onJson={() => download(`${selected.generation_context_id}-worker-context.json`, workerContextText(), "application/json")} /><DetailPanel title="Assembled generation context items" text={assembledContextText()} onCopy={() => copy(assembledContextText())} onText={() => download(`${selected.generation_context_id}-context.txt`, assembledContextText(), "text/plain")} onJson={() => download(`${selected.generation_context_id}-context.json`, assembledContextText(), "application/json")} /></div> : <p>Select a generation context to inspect its prompt and assembled context.</p>}</section></div>
  </main>;
}

function DetailPanel({ title, text, onCopy, onText, onJson }: { title: string; text: string; onCopy: () => void; onText: () => void; onJson: () => void }) {
  return <article style={{ border: "1px solid #dbe2e8", borderRadius: 8, padding: 12 }}><div style={{ display: "flex", justifyContent: "space-between", gap: 8, flexWrap: "wrap" }}><h3>{title}</h3><div><button onClick={onCopy}>Copy</button> <button onClick={onText}>Download text</button> <button onClick={onJson}>Download JSON</button></div></div><pre style={{ maxHeight: 440, overflow: "auto", whiteSpace: "pre-wrap", overflowWrap: "anywhere", background: "#111923", color: "#d9e2ec", padding: 12 }}>{text}</pre></article>;
}
