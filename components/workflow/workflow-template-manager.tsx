"use client";

import { useEffect, useState } from "react";
import {
  createWorkflowTemplateVersion,
  deactivateWorkflowTemplate,
  getWorkflowTemplate,
  listWorkflowTemplates,
  reactivateWorkflowTemplate,
  type WorkflowTemplate,
  type WorkflowTemplateDetail,
} from "@/lib/api/campaigns";
import { useI18n } from "@/lib/i18n/context";
import { formatDateTime } from "@/lib/i18n/format";

export function WorkflowTemplateManager() {
  const { t, locale } = useI18n();
  const [templates, setTemplates] = useState<WorkflowTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedTemplateId, setSelectedTemplateId] = useState("");
  const [detail, setDetail] = useState<WorkflowTemplateDetail | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;

    async function loadTemplates() {
      setLoading(true);
      try {
        const rows = await listWorkflowTemplates();
        if (!mounted) return;
        setTemplates(rows);
        if (rows.length > 0) {
          setSelectedTemplateId(rows[0].template_id);
        }
      } catch {
        if (!mounted) return;
        setTemplates([]);
      } finally {
        if (mounted) setLoading(false);
      }
    }

    loadTemplates();
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    if (!selectedTemplateId) return;

    let mounted = true;
    async function loadDetail() {
      try {
        const data = await getWorkflowTemplate(selectedTemplateId);
        if (!mounted) return;
        setDetail(data);
      } catch {
        if (!mounted) return;
        setDetail(null);
      }
    }

    loadDetail();
    return () => {
      mounted = false;
    };
  }, [selectedTemplateId]);

  async function handleCloneVersion() {
    if (!detail) return;

    const active = detail.versions.find((item) => item.version === detail.template.active_version);
    if (!active) return;

    try {
      const updated = await createWorkflowTemplateVersion(detail.template.template_id, active.tasks);
      setDetail(updated);
      setTemplates((prev) => prev.map((item) => (item.template_id === updated.template.template_id ? updated.template : item)));
      setMessage(t("workflowTemplates.cloneSuccess"));
    } catch {
      setMessage(t("workflowTemplates.cloneFailed"));
    }
  }

  async function handleToggleTemplateStatus(template: WorkflowTemplate) {
    try {
      if (template.status === "inactive") {
        await reactivateWorkflowTemplate(template.template_id);
      } else {
        await deactivateWorkflowTemplate(template.template_id);
      }
      const rows = await listWorkflowTemplates();
      setTemplates(rows);
      setDetail((prev) => prev && prev.template.template_id === template.template_id ? { ...prev, template: { ...prev.template, status: template.status === "inactive" ? "active" : "inactive" } } : prev);
      setMessage(template.status === "inactive" ? t("workflowTemplates.reactivateSuccess") : t("workflowTemplates.deactivateSuccess"));
    } catch {
      setMessage(t("workflowTemplates.statusFailed"));
    }
  }

  return (
    <section className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">{t("workflowTemplates.title")}</h1>
        <p className="text-sm text-slate-500">{t("workflowTemplates.subtitle")}</p>
      </header>

      {message ? <p className="rounded-xl bg-blue-50 px-3 py-2 text-sm text-blue-700">{message}</p> : null}

      {loading ? (
        <article className="rounded-2xl border border-slate-200 bg-white p-4 text-sm text-slate-500 dark:border-slate-800 dark:bg-slate-900">
          {t("workflowTemplates.loading")}
        </article>
      ) : templates.length === 0 ? (
        <article className="rounded-2xl border border-slate-200 bg-white p-4 text-sm text-slate-500 dark:border-slate-800 dark:bg-slate-900">
          {t("workflowTemplates.empty")}
        </article>
      ) : (
        <div className="grid gap-4 xl:grid-cols-[1.2fr_1fr]">
          <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
            <table className="min-w-full text-left text-sm">
              <thead className="border-b border-slate-200 bg-slate-50 text-slate-500 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-400">
                <tr>
                  <th className="px-4 py-3">{t("workflowTemplates.table.name")}</th>
                  <th className="px-4 py-3">{t("workflowTemplates.table.description")}</th>
                  <th className="px-4 py-3">{t("workflowTemplates.table.version")}</th>
                  <th className="px-4 py-3">{t("workflowTemplates.table.created")}</th>
                  <th className="px-4 py-3">{t("workflowTemplates.table.actions")}</th>
                </tr>
              </thead>
              <tbody>
                {templates.map((template) => (
                  <tr
                    key={template.template_id}
                    className={`cursor-pointer border-b border-slate-200/70 last:border-none dark:border-slate-800 ${selectedTemplateId === template.template_id ? "bg-blue-50/50 dark:bg-blue-900/20" : ""}`}
                    onClick={() => setSelectedTemplateId(template.template_id)}
                  >
                    <td className="px-4 py-3 font-medium">{template.name}</td>
                    <td className="px-4 py-3 text-slate-600 dark:text-slate-300">{template.description}</td>
                    <td className="px-4 py-3">{t("workflowTemplates.activeVersion", { version: template.active_version })}</td>
                    <td className="px-4 py-3">{formatDateTime(locale, template.created_at)}</td>
                    <td className="px-4 py-3">
                      <button
                        onClick={(event) => {
                          event.stopPropagation();
                          void handleToggleTemplateStatus(template);
                        }}
                        className="rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs font-medium dark:border-slate-700"
                      >
                        {template.status === "inactive" ? t("workflowTemplates.reactivate") : t("workflowTemplates.deactivate")}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="space-y-3 rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold">{t("workflowTemplates.detailTitle")}</h2>
              <button
                onClick={handleCloneVersion}
                disabled={!detail}
                className="rounded-lg bg-slate-900 px-2.5 py-1.5 text-xs font-medium text-white disabled:opacity-50 dark:bg-slate-700"
              >
                {t("workflowTemplates.cloneVersion")}
              </button>
            </div>

            {!detail ? (
              <p className="text-sm text-slate-500">{t("workflowTemplates.noDetail")}</p>
            ) : (
              <div className="space-y-2 text-sm">
                <p className="font-medium">{detail.template.name}</p>
                <p className="text-slate-500">{t("workflowTemplates.activeVersion", { version: detail.template.active_version })}</p>
                <div className="max-h-[360px] space-y-2 overflow-auto rounded-xl border border-slate-200 p-3 dark:border-slate-700">
                  {detail.versions
                    .slice()
                    .sort((a, b) => b.version - a.version)
                    .map((version) => (
                      <article key={version.version} className="rounded-lg bg-slate-50 p-2.5 dark:bg-slate-950">
                        <p className="font-medium">{t("workflowTemplates.activeVersion", { version: version.version })}</p>
                        <p className="text-xs text-slate-500">{formatDateTime(locale, version.created_at)}</p>
                        <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">{version.tasks.map((task) => task.task_type).join(" → ")}</p>
                      </article>
                    ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
