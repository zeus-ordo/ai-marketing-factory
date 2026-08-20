"use client";

import { useState } from "react";
import {
  platformListCompanies,
  platformCreateCompany,
  platformCreateAdmin,
  platformListMembers,
  platformListAuditLogs,
  platformListLlmUsage,
  platformSummarizeLlmUsage,
  platformListPricing,
  platformUpsertPricing,
  platformDeletePricing,
  setPlatformKey,
  type CompanyResponse,
  type MemberResponse,
  type AuditLogEntry,
  type LlmUsageRecord,
  type LlmUsageSummaryResponse,
  type LlmModelPricingRecord,
} from "@/lib/api/auth";
import { useI18n } from "@/lib/i18n/context";

export default function AdminPlatformPage() {
  const { t } = useI18n();
  const usageModelOptions = ["deepseek-v3", "minimax-video-01"];
  const [companies, setCompanies] = useState<CompanyResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [platformKeyInput, setPlatformKeyInput] = useState("");
  const [keyError, setKeyError] = useState<string | null>(null);

  const [newCoName, setNewCoName] = useState("");
  const [newCoSlug, setNewCoSlug] = useState("");
  const [createCoMsg, setCreateCoMsg] = useState<string | null>(null);

  const [adminCompanyId, setAdminCompanyId] = useState("");
  const [adminEmail, setAdminEmail] = useState("");
  const [adminPassword, setAdminPassword] = useState("");
  const [adminMsg, setAdminMsg] = useState<string | null>(null);

  const [selectedCompanyId, setSelectedCompanyId] = useState<string | null>(null);
  const [members, setMembers] = useState<MemberResponse[]>([]);

  // Audit logs
  const [auditLogs, setAuditLogs] = useState<AuditLogEntry[]>([]);
  const [auditPage, setAuditPage] = useState(1);
  const [auditTotal, setAuditTotal] = useState(0);
  const [auditActionFilter, setAuditActionFilter] = useState("");
  const [loadingLogs, setLoadingLogs] = useState(false);

  // Tabs
  const [activeTab, setActiveTab] = useState<"auditLogs" | "usage" | "pricing">("auditLogs");

  // LLM Usage tab state
  const [usageSummary, setUsageSummary] = useState<LlmUsageSummaryResponse | null>(null);
  const [usageList, setUsageList] = useState<LlmUsageRecord[]>([]);
  const [usagePage, setUsagePage] = useState(1);
  const [usageTotal, setUsageTotal] = useState(0);
  const [usageFrom, setUsageFrom] = useState("");
  const [usageTo, setUsageTo] = useState("");
  const [usageCompanyId, setUsageCompanyId] = useState("");
  const [usageModel, setUsageModel] = useState("");
  const [loadingUsage, setLoadingUsage] = useState(false);

  // Pricing tab state
  const [pricingList, setPricingList] = useState<LlmModelPricingRecord[]>([]);
  const [pricingModalOpen, setPricingModalOpen] = useState(false);
  const [editingPricing, setEditingPricing] = useState<LlmModelPricingRecord | null>(null);
  const [pricingFormModel, setPricingFormModel] = useState("");
  const [pricingFormProvider, setPricingFormProvider] = useState("");
  const [pricingFormPrompt, setPricingFormPrompt] = useState(0);
  const [pricingFormCompletion, setPricingFormCompletion] = useState(0);
  const [pricingMsg, setPricingMsg] = useState<string | null>(null);
  const [loadingPricing, setLoadingPricing] = useState(false);

  function handleKeyChange(e: React.ChangeEvent<HTMLInputElement>) {
    const val = e.target.value;
    setPlatformKeyInput(val);
    setPlatformKey(val);
    setKeyError(null);
  }

  async function handleLoadCompanies() {
    if (!platformKeyInput.trim()) {
      setKeyError(t("admin.enterPlatformKey"));
      return;
    }
    setLoading(true);
    try {
      const res = await platformListCompanies();
      setCompanies(res.items);
      // Load audit logs in parallel
      handleLoadAuditLogs(1);
    } catch (err) {
      setKeyError(err instanceof Error ? err.message : t("admin.failed"));
    } finally {
      setLoading(false);
    }
  }

  async function handleCreateCompany(e: React.FormEvent) {
    e.preventDefault();
    if (!platformKeyInput.trim()) return;
    setCreateCoMsg(null);
    try {
      const created = await platformCreateCompany(newCoName, newCoSlug);
      setCompanies((prev) => [created, ...prev]);
      setNewCoName("");
      setNewCoSlug("");
      setCreateCoMsg(t("admin.companyCreated"));
    } catch (err) {
      setCreateCoMsg(err instanceof Error ? err.message : t("admin.failed"));
    }
  }

  async function handleCreateAdmin(e: React.FormEvent) {
    e.preventDefault();
    if (!platformKeyInput.trim() || !adminCompanyId) return;
    setAdminMsg(null);
    try {
      await platformCreateAdmin(adminCompanyId, adminEmail, adminPassword);
      setAdminEmail("");
      setAdminPassword("");
      setAdminMsg(t("admin.adminCreated"));
    } catch (err) {
      setAdminMsg(err instanceof Error ? err.message : t("admin.failed"));
    }
  }

  async function handleViewMembers(companyId: string) {
    if (!platformKeyInput.trim()) return;
    setSelectedCompanyId(companyId);
    try {
      const res = await platformListMembers(companyId);
      setMembers(res.items);
    } catch {
      setMembers([]);
    }
  }

  async function handleLoadAuditLogs(page = 1) {
    if (!platformKeyInput.trim()) return;
    setLoadingLogs(true);
    setAuditPage(page);
    try {
      const res = await platformListAuditLogs({
        page,
        page_size: 20,
        action: auditActionFilter || undefined,
      });
      setAuditLogs(res.items);
      setAuditTotal(res.total);
    } catch {
      setAuditLogs([]);
    } finally {
      setLoadingLogs(false);
    }
  }

  async function handleLoadUsage(page = 1) {
    if (!platformKeyInput.trim()) return;
    setLoadingUsage(true);
    setUsagePage(page);
    try {
      const [summaryRes, listRes] = await Promise.all([
        platformSummarizeLlmUsage({
          company_id: usageCompanyId || undefined,
          from: usageFrom || undefined,
          to: usageTo || undefined,
        }),
        platformListLlmUsage({
          page,
          page_size: 20,
          company_id: usageCompanyId || undefined,
          model: usageModel || undefined,
          from: usageFrom || undefined,
          to: usageTo || undefined,
        }),
      ]);
      setUsageSummary(summaryRes);
      setUsageList(listRes.items);
      setUsageTotal(listRes.total);
    } catch {
      setUsageSummary(null);
      setUsageList([]);
    } finally {
      setLoadingUsage(false);
    }
  }

  async function handleLoadPricing() {
    if (!platformKeyInput.trim()) return;
    setLoadingPricing(true);
    try {
      const res = await platformListPricing();
      setPricingList(res.items);
    } catch {
      setPricingList([]);
    } finally {
      setLoadingPricing(false);
    }
  }

  function openAddPricing() {
    setEditingPricing(null);
    setPricingFormModel("");
    setPricingFormProvider("");
    setPricingFormPrompt(0);
    setPricingFormCompletion(0);
    setPricingMsg(null);
    setPricingModalOpen(true);
  }

  function openEditPricing(p: LlmModelPricingRecord) {
    setEditingPricing(p);
    setPricingFormModel(p.model);
    setPricingFormProvider(p.provider);
    setPricingFormPrompt(p.prompt_price_per_m);
    setPricingFormCompletion(p.completion_price_per_m);
    setPricingMsg(null);
    setPricingModalOpen(true);
  }

  async function handleSavePricing() {
    if (!platformKeyInput.trim()) return;
    setPricingMsg(null);
    try {
      await platformUpsertPricing({
        model: pricingFormModel,
        provider: pricingFormProvider,
        prompt_price_per_m: pricingFormPrompt,
        completion_price_per_m: pricingFormCompletion,
      });
      setPricingMsg(t("admin.usage.saved"));
      setPricingModalOpen(false);
      await handleLoadPricing();
    } catch (err) {
      setPricingMsg(err instanceof Error ? err.message : t("admin.failed"));
    }
  }

  async function handleDeletePricing() {
    if (!platformKeyInput.trim() || !editingPricing) return;
    setPricingMsg(null);
    try {
      await platformDeletePricing(editingPricing.model);
      setPricingMsg(t("admin.usage.deleted"));
      setPricingModalOpen(false);
      await handleLoadPricing();
    } catch (err) {
      setPricingMsg(err instanceof Error ? err.message : t("admin.failed"));
    }
  }

  const tabBar = (
    <div className="flex border-b border-slate-200 dark:border-slate-800 mb-4">
      <button
        onClick={() => setActiveTab("auditLogs")}
        className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
          activeTab === "auditLogs"
            ? "border-[#0071e3] text-[#0071e3]"
            : "border-transparent text-slate-500 hover:text-slate-700"
        }`}
      >
        {t("admin.auditLogs")}
      </button>
      <button
        onClick={() => { setActiveTab("usage"); }}
        className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
          activeTab === "usage"
            ? "border-[#0071e3] text-[#0071e3]"
            : "border-transparent text-slate-500 hover:text-slate-700"
        }`}
      >
        {t("admin.usage.title")}
      </button>
      <button
        onClick={() => { setActiveTab("pricing"); handleLoadPricing(); }}
        className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
          activeTab === "pricing"
            ? "border-[#0071e3] text-[#0071e3]"
            : "border-transparent text-slate-500 hover:text-slate-700"
        }`}
      >
        {t("admin.usage.pricing")}
      </button>
    </div>
  );

  const usageTab = (
    <>
      {/* Summary Cards */}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4 mb-4">
        <div className="rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
          <p className="text-xs text-slate-500">{t("admin.usage.totalPromptTokens")}</p>
          <p className="mt-1 text-2xl font-semibold">
            {usageSummary ? usageSummary.total_prompt_tokens.toLocaleString() : "—"}
          </p>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
          <p className="text-xs text-slate-500">{t("admin.usage.totalCompletionTokens")}</p>
          <p className="mt-1 text-2xl font-semibold">
            {usageSummary ? usageSummary.total_completion_tokens.toLocaleString() : "—"}
          </p>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
          <p className="text-xs text-slate-500">{t("admin.usage.totalCost")}</p>
          <p className="mt-1 text-2xl font-semibold">
            {usageSummary ? `$${usageSummary.total_cost_usd.toFixed(4)}` : "—"}
          </p>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
          <p className="text-xs text-slate-500">{t("admin.usage.totalRequests")}</p>
          <p className="mt-1 text-2xl font-semibold">
            {usageSummary ? usageSummary.total_request_count.toLocaleString() : "—"}
          </p>
        </div>
      </div>

      {/* Filter Bar */}
      <div className="flex flex-wrap gap-3 mb-4">
        <input
          type="date"
          value={usageFrom}
          onChange={(e) => setUsageFrom(e.target.value)}
          className="rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
        />
        <input
          type="date"
          value={usageTo}
          onChange={(e) => setUsageTo(e.target.value)}
          className="rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
        />
        <select
          value={usageCompanyId}
          onChange={(e) => setUsageCompanyId(e.target.value)}
          className="rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
        >
          <option value="">{t("admin.usage.allCompanies")}</option>
          {companies.map((c) => (
            <option key={c.company_id} value={c.company_id}>{c.name}</option>
          ))}
        </select>
        <select
          value={usageModel}
          onChange={(e) => setUsageModel(e.target.value)}
          className="rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
        >
          <option value="">{t("admin.usage.allModels")}</option>
          {usageModelOptions.map((model) => (
            <option key={model} value={model}>{model}</option>
          ))}
        </select>
        <button
          onClick={() => handleLoadUsage(1)}
          className="rounded-lg bg-[#0071e3] px-4 py-2 text-sm font-medium text-white hover:bg-[#0071e3]/90"
        >
          {t("admin.usage.filter")}
        </button>
      </div>

      {/* By-Model Table */}
      {usageSummary && usageSummary.by_model.length > 0 && (
        <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 mb-4">
          <header className="border-b border-slate-200 px-4 py-3 text-sm font-semibold dark:border-slate-800">
            {t("admin.usage.byModel")}
          </header>
          <table className="min-w-full text-left text-sm">
            <thead className="border-b border-slate-200 bg-slate-50 text-slate-500 dark:border-slate-800 dark:bg-slate-950">
              <tr>
                <th className="px-4 py-3">{t("admin.usage.model")}</th>
                <th className="px-4 py-3">{t("admin.usage.provider")}</th>
                <th className="px-4 py-3">{t("admin.usage.promptTokens")}</th>
                <th className="px-4 py-3">{t("admin.usage.completionTokens")}</th>
                <th className="px-4 py-3">{t("admin.usage.cost")}</th>
                <th className="px-4 py-3">{t("admin.usage.requestCount")}</th>
              </tr>
            </thead>
            <tbody>
              {usageSummary.by_model.map((row) => (
                <tr key={row.model} className="border-b border-slate-200/70 last:border-none dark:border-slate-800">
                  <td className="px-4 py-3 font-medium">{row.model}</td>
                  <td className="px-4 py-3 text-slate-500">{row.provider}</td>
                  <td className="px-4 py-3 text-slate-500">{row.prompt_tokens.toLocaleString()}</td>
                  <td className="px-4 py-3 text-slate-500">{row.completion_tokens.toLocaleString()}</td>
                  <td className="px-4 py-3 text-slate-500">${row.cost_usd.toFixed(4)}</td>
                  <td className="px-4 py-3 text-slate-500">{row.request_count.toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Detailed List */}
      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
        <header className="border-b border-slate-200 px-4 py-3 text-sm font-semibold dark:border-slate-800">
          {t("admin.usage.title")}
        </header>
        {loadingUsage ? (
          <p className="px-4 py-8 text-center text-slate-500">{t("admin.loading")}</p>
        ) : usageList.length === 0 ? (
          <p className="px-4 py-8 text-center text-slate-500">{t("admin.usage.noData")}</p>
        ) : (
          <table className="min-w-full text-left text-sm">
            <thead className="border-b border-slate-200 bg-slate-50 text-slate-500 dark:border-slate-800 dark:bg-slate-950">
              <tr>
                <th className="px-4 py-3">{t("admin.date")}</th>
                <th className="px-4 py-3">{t("admin.usage.model")}</th>
                <th className="px-4 py-3">{t("admin.usage.provider")}</th>
                <th className="px-4 py-3">{t("admin.usage.promptTokens")}</th>
                <th className="px-4 py-3">{t("admin.usage.completionTokens")}</th>
                <th className="px-4 py-3">{t("admin.usage.cost")}</th>
                <th className="px-4 py-3">{t("admin.usage.requestCount")}</th>
              </tr>
            </thead>
            <tbody>
              {usageList.map((item) => (
                <tr key={item.usage_id} className="border-b border-slate-200/70 last:border-none dark:border-slate-800">
                  <td className="px-4 py-3 text-slate-500">{new Date(item.created_at).toLocaleString()}</td>
                  <td className="px-4 py-3 font-medium">{item.model}</td>
                  <td className="px-4 py-3 text-slate-500">{item.provider}</td>
                  <td className="px-4 py-3 text-slate-500">{item.prompt_tokens.toLocaleString()}</td>
                  <td className="px-4 py-3 text-slate-500">{item.completion_tokens.toLocaleString()}</td>
                  <td className="px-4 py-3 text-slate-500">${item.cost_usd.toFixed(4)}</td>
                  <td className="px-4 py-3 text-slate-500">{item.request_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {usageTotal > 20 && (
          <div className="flex items-center justify-between border-t border-slate-200 px-4 py-3 dark:border-slate-800">
            <span className="text-xs text-slate-500">
              {t("common.page", { page: usagePage, total: Math.ceil(usageTotal / 20) })}
            </span>
            <div className="flex gap-2">
              <button
                onClick={() => handleLoadUsage(usagePage - 1)}
                disabled={usagePage <= 1}
                className="rounded-lg border border-slate-300 px-3 py-1 text-xs disabled:opacity-50 dark:border-slate-700"
              >
                {t("common.prev")}
              </button>
              <button
                onClick={() => handleLoadUsage(usagePage + 1)}
                disabled={usagePage * 20 >= usageTotal}
                className="rounded-lg border border-slate-300 px-3 py-1 text-xs disabled:opacity-50 dark:border-slate-700"
              >
                {t("common.next")}
              </button>
            </div>
          </div>
        )}
      </div>
    </>
  );

  const pricingTab = (
    <>
      <div className="flex justify-end mb-4">
        <button
          onClick={openAddPricing}
          className="rounded-lg bg-[#0071e3] px-4 py-2 text-sm font-medium text-white hover:bg-[#0071e3]/90"
        >
          {t("admin.usage.addPricing")}
        </button>
      </div>

      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
        <header className="border-b border-slate-200 px-4 py-3 text-sm font-semibold dark:border-slate-800">
          {t("admin.usage.pricing")}
        </header>
        {loadingPricing ? (
          <p className="px-4 py-8 text-center text-slate-500">{t("admin.loading")}</p>
        ) : pricingList.length === 0 ? (
          <p className="px-4 py-8 text-center text-slate-500">{t("admin.usage.noData")}</p>
        ) : (
          <table className="min-w-full text-left text-sm">
            <thead className="border-b border-slate-200 bg-slate-50 text-slate-500 dark:border-slate-800 dark:bg-slate-950">
              <tr>
                <th className="px-4 py-3">{t("admin.usage.model")}</th>
                <th className="px-4 py-3">{t("admin.usage.provider")}</th>
                <th className="px-4 py-3">{t("admin.usage.promptPricePerM")}</th>
                <th className="px-4 py-3">{t("admin.usage.completionPricePerM")}</th>
                <th className="px-4 py-3">{t("admin.usage.status")}</th>
                <th className="px-4 py-3">{t("members.actions")}</th>
              </tr>
            </thead>
            <tbody>
              {pricingList.map((p) => (
                <tr key={p.pricing_id} className="border-b border-slate-200/70 last:border-none dark:border-slate-800">
                  <td className="px-4 py-3 font-medium">{p.model}</td>
                  <td className="px-4 py-3 text-slate-500">{p.provider}</td>
                  <td className="px-4 py-3 text-slate-500">${p.prompt_price_per_m}</td>
                  <td className="px-4 py-3 text-slate-500">${p.completion_price_per_m}</td>
                  <td className="px-4 py-3">
                    <span className={`rounded-full px-2 py-0.5 text-xs ${
                      p.is_active ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-500"
                    }`}>
                      {p.is_active ? t("admin.usage.active") : t("admin.usage.inactive")}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <button
                      onClick={() => openEditPricing(p)}
                      className="text-xs text-primary hover:underline"
                    >
                      {t("admin.usage.editPricing")}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Modal */}
      {pricingModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-6 dark:border-slate-800 dark:bg-slate-900 space-y-4">
            <h3 className="text-lg font-semibold">
              {editingPricing ? t("admin.usage.editPricing") : t("admin.usage.addPricing")}
            </h3>
            <div className="space-y-3">
              <input
                type="text"
                value={pricingFormModel}
                onChange={(e) => setPricingFormModel(e.target.value)}
                placeholder={t("admin.usage.model")}
                disabled={!!editingPricing}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950 disabled:opacity-50"
              />
              <input
                type="text"
                value={pricingFormProvider}
                onChange={(e) => setPricingFormProvider(e.target.value)}
                placeholder={t("admin.usage.provider")}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
              />
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-slate-500 mb-1">{t("admin.usage.promptPricePerM")}</label>
                  <input
                    type="number"
                    step="0.0001"
                    value={pricingFormPrompt}
                    onChange={(e) => setPricingFormPrompt(parseFloat(e.target.value) || 0)}
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
                  />
                </div>
                <div>
                  <label className="block text-xs text-slate-500 mb-1">{t("admin.usage.completionPricePerM")}</label>
                  <input
                    type="number"
                    step="0.0001"
                    value={pricingFormCompletion}
                    onChange={(e) => setPricingFormCompletion(parseFloat(e.target.value) || 0)}
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
                  />
                </div>
              </div>
            </div>
            {pricingMsg && <p className="text-xs text-emerald-600">{pricingMsg}</p>}
            <div className="flex justify-between">
              <div>
                {editingPricing && (
                  <button
                    onClick={handleDeletePricing}
                    className="rounded-lg border border-rose-300 px-4 py-2 text-sm font-medium text-rose-600 hover:bg-rose-50"
                  >
                    {t("review.reject")}
                  </button>
                )}
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => setPricingModalOpen(false)}
                  className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium dark:border-slate-700"
                >
                  {t("common.cancel")}
                </button>
                <button
                  onClick={handleSavePricing}
                  className="rounded-lg bg-[#0071e3] px-4 py-2 text-sm font-medium text-white hover:bg-[#0071e3]/90"
                >
                  {t("common.apply")}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">{t("admin.title")}</h1>
        <p className="mt-1 text-sm text-slate-500">{t("admin.platformKey")}</p>
      </header>

      <div className="rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
        <h2 className="mb-3 text-sm font-semibold">{t("admin.platformKey")}</h2>
        <div className="flex gap-3">
          <input
            type="password"
            value={platformKeyInput}
            onChange={handleKeyChange}
            placeholder={t("admin.platformKeyPlaceholder")}
            className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
          />
          <button
            onClick={handleLoadCompanies}
            className="rounded-lg bg-[#0071e3] px-4 py-2 text-sm font-medium text-white hover:bg-[#0071e3]/90"
          >
            {t("admin.load")}
          </button>
        </div>
        {keyError && <p className="mt-2 text-xs text-rose-600">{keyError}</p>}
      </div>

      {/* System Overview */}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <div className="rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
          <p className="text-xs text-slate-500">{t("admin.totalCompanies")}</p>
          <p className="mt-1 text-2xl font-semibold">{companies.length}</p>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
          <p className="text-xs text-slate-500">{t("admin.totalMembers")}</p>
          <p className="mt-1 text-2xl font-semibold">
            {companies.length > 0 ? "—" : "—"}
          </p>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
          <p className="text-xs text-slate-500">{t("admin.auditLogs")}</p>
          <p className="mt-1 text-2xl font-semibold">{auditTotal > 0 ? auditTotal : "—"}</p>
        </div>
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <div className="rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
          <h2 className="mb-3 text-sm font-semibold">{t("admin.createCompany")}</h2>
          <form onSubmit={handleCreateCompany} className="space-y-3">
            <input
              type="text"
              value={newCoName}
              onChange={(e) => setNewCoName(e.target.value)}
              placeholder={t("admin.companyName")}
              required
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
            />
            <input
              type="text"
              value={newCoSlug}
              onChange={(e) => setNewCoSlug(e.target.value)}
              placeholder={t("admin.slug")}
              required
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
            />
            <button
              type="submit"
              className="w-full rounded-lg bg-[#0071e3] px-4 py-2 text-sm font-medium text-white hover:bg-[#0071e3]/90"
            >
              {t("admin.createCompanyButton")}
            </button>
            {createCoMsg && <p className="text-xs text-emerald-600">{createCoMsg}</p>}
          </form>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
          <h2 className="mb-3 text-sm font-semibold">{t("admin.createAdmin")}</h2>
          <form onSubmit={handleCreateAdmin} className="space-y-3">
            <select
              value={adminCompanyId}
              onChange={(e) => setAdminCompanyId(e.target.value)}
              required
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
            >
              <option value="">{t("admin.selectCompany")}</option>
              {companies.map((c) => (
                <option key={c.company_id} value={c.company_id}>
                  {c.name}
                </option>
              ))}
            </select>
            <input
              type="email"
              value={adminEmail}
              onChange={(e) => setAdminEmail(e.target.value)}
              placeholder={t("admin.adminEmail")}
              required
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
            />
            <input
              type="password"
              value={adminPassword}
              onChange={(e) => setAdminPassword(e.target.value)}
              placeholder={t("admin.adminPassword")}
              required
              minLength={8}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
            />
            <button
              type="submit"
              className="w-full rounded-lg bg-[#0071e3] px-4 py-2 text-sm font-medium text-white hover:bg-[#0071e3]/90"
            >
              {t("admin.createAdminButton")}
            </button>
            {adminMsg && <p className="text-xs text-emerald-600">{adminMsg}</p>}
          </form>
        </div>
      </div>

      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
        <header className="border-b border-slate-200 px-4 py-3 text-sm font-semibold dark:border-slate-800">
          {t("admin.companies")} ({companies.length})
        </header>
        {loading ? (
          <p className="px-4 py-8 text-center text-slate-500">{t("admin.loading")}</p>
        ) : companies.length === 0 ? (
          <p className="px-4 py-8 text-center text-slate-500">{t("admin.noCompanies")}</p>
        ) : (
          <table className="min-w-full text-left text-sm">
            <thead className="border-b border-slate-200 bg-slate-50 text-slate-500 dark:border-slate-800 dark:bg-slate-950">
              <tr>
                <th className="px-4 py-3">{t("admin.companyName")}</th>
                <th className="px-4 py-3">{t("admin.slug")}</th>
                <th className="px-4 py-3">{t("admin.created")}</th>
                <th className="px-4 py-3">{t("members.actions")}</th>
              </tr>
            </thead>
            <tbody>
              {companies.map((c) => (
                <tr key={c.company_id} className="border-b border-slate-200/70 last:border-none dark:border-slate-800">
                  <td className="px-4 py-3 font-medium">{c.name}</td>
                  <td className="px-4 py-3 text-slate-500">{c.slug}</td>
                  <td className="px-4 py-3 text-slate-500">{new Date(c.created_at).toLocaleDateString()}</td>
                  <td className="px-4 py-3">
                    <button
                      onClick={() => handleViewMembers(c.company_id)}
                      className="text-xs text-primary hover:underline"
                    >
                      {t("admin.viewMembers")}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {selectedCompanyId && (
        <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
          <header className="border-b border-slate-200 px-4 py-3 text-sm font-semibold dark:border-slate-800">
            {t("admin.companyMembers")}
          </header>
          {members.length === 0 ? (
            <p className="px-4 py-8 text-center text-slate-500">{t("admin.noMembers")}</p>
          ) : (
            <table className="min-w-full text-left text-sm">
              <thead className="border-b border-slate-200 bg-slate-50 text-slate-500 dark:border-slate-800 dark:bg-slate-950">
                <tr>
                  <th className="px-4 py-3">{t("members.email")}</th>
                  <th className="px-4 py-3">{t("members.roles")}</th>
                  <th className="px-4 py-3">{t("members.status")}</th>
                </tr>
              </thead>
              <tbody>
                {members.map((m) => (
                  <tr key={m.member_id} className="border-b border-slate-200/70 last:border-none dark:border-slate-800">
                    <td className="px-4 py-3 font-medium">{m.email}</td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-1">
                        {m.roles.map((r) => (
                          <span key={r.role_id} className="rounded-full bg-slate-100 px-2 py-0.5 text-xs">
                            {r.name}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`rounded-full px-2 py-0.5 text-xs ${
                        m.email_verified ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700"
                      }`}>
                        {m.email_verified ? t("admin.verified") : t("admin.pending")}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* Tabs */}
      {tabBar}

      {/* Audit Logs */}
      {activeTab === "auditLogs" && (
      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
        <header className="flex items-center justify-between border-b border-slate-200 px-4 py-3 dark:border-slate-800">
          <span className="text-sm font-semibold">{t("admin.auditLogs")}</span>
          <div className="flex items-center gap-2">
            <input
              type="text"
              value={auditActionFilter}
              onChange={(e) => setAuditActionFilter(e.target.value)}
              placeholder={t("admin.filterByAction")}
              className="rounded-lg border border-slate-300 px-2 py-1 text-xs dark:border-slate-700 dark:bg-slate-950"
            />
            <button
              onClick={() => handleLoadAuditLogs(1)}
              className="rounded-lg bg-[#0071e3] px-3 py-1 text-xs font-medium text-white hover:bg-[#0071e3]/90"
            >
              {t("common.search")}
            </button>
          </div>
        </header>
        {loadingLogs ? (
          <p className="px-4 py-8 text-center text-slate-500">{t("admin.loading")}</p>
        ) : auditLogs.length === 0 ? (
          <p className="px-4 py-8 text-center text-slate-500">{t("admin.noLogs")}</p>
        ) : (
          <table className="min-w-full text-left text-sm">
            <thead className="border-b border-slate-200 bg-slate-50 text-slate-500 dark:border-slate-800 dark:bg-slate-950">
              <tr>
                <th className="px-4 py-3">{t("admin.date")}</th>
                <th className="px-4 py-3">{t("admin.action")}</th>
                <th className="px-4 py-3">{t("admin.member")}</th>
                <th className="px-4 py-3">{t("admin.resource")}</th>
                <th className="px-4 py-3">{t("admin.ipAddress")}</th>
              </tr>
            </thead>
            <tbody>
              {auditLogs.map((log) => (
                <tr key={log.log_id} className="border-b border-slate-200/70 last:border-none dark:border-slate-800">
                  <td className="px-4 py-3 text-slate-500">
                    {new Date(log.created_at).toLocaleString()}
                  </td>
                  <td className="px-4 py-3">
                    <span className="rounded-full bg-blue-100 px-2 py-0.5 text-xs text-blue-700">
                      {log.action}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-slate-500">{log.member_id ?? "—"}</td>
                  <td className="px-4 py-3 text-slate-500">
                    {log.resource_type ? (
                      <span>
                        {log.resource_type}
                        {log.resource_id ? ` / ${log.resource_id}` : ""}
                      </span>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className="px-4 py-3 text-slate-500">{log.ip_address ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {auditTotal > 20 && (
          <div className="flex items-center justify-between border-t border-slate-200 px-4 py-3 dark:border-slate-800">
            <span className="text-xs text-slate-500">
              {t("common.page", { page: auditPage, total: Math.ceil(auditTotal / 20) })}
            </span>
            <div className="flex gap-2">
              <button
                onClick={() => handleLoadAuditLogs(auditPage - 1)}
                disabled={auditPage <= 1}
                className="rounded-lg border border-slate-300 px-3 py-1 text-xs disabled:opacity-50 dark:border-slate-700"
              >
                {t("common.prev")}
              </button>
              <button
                onClick={() => handleLoadAuditLogs(auditPage + 1)}
                disabled={auditPage * 20 >= auditTotal}
                className="rounded-lg border border-slate-300 px-3 py-1 text-xs disabled:opacity-50 dark:border-slate-700"
              >
                {t("common.next")}
              </button>
            </div>
          </div>
        )}
      </div>
      )}

      {/* Usage Tab */}
      {activeTab === "usage" && usageTab}

      {/* Pricing Tab */}
      {activeTab === "pricing" && pricingTab}
    </div>
  );
}
