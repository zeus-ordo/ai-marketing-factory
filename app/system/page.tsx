"use client";

import { useEffect, useMemo, useState } from "react";
import {
  getSystemOperationAuditCsvUrl,
  getSystemOperationAuditLogs,
  getSystemQueueHealth,
  purgeQueueTopic,
  runSlaScan,
  retryDlqMessage,
  runSystemHealthCheck,
  getRedisStats,
  type OperationAuditEntry,
  type QueueHealthResponse,
  type RedisStats,
} from "@/lib/api/campaigns";
import { useI18n, type TranslateFunction } from "@/lib/i18n/context";
import { formatDateTime } from "@/lib/i18n/format";

const fallback: QueueHealthResponse = {
  topics: [
    { topic: "task.copy", length: 0, pending: 0, lag: 0 },
    { topic: "task.image", length: 0, pending: 0, lag: 0 },
    { topic: "task.video", length: 0, pending: 0, lag: 0 },
    { topic: "task.ads", length: 0, pending: 0, lag: 0 },
  ],
  dlq_size: 0,
  dlq_recent: [],
};

export default function SystemPage() {
  const { t, locale } = useI18n();
  const [health, setHealth] = useState<QueueHealthResponse>(fallback);
  const [loading, setLoading] = useState(true);
  const [fallbackMode, setFallbackMode] = useState(false);
  const [opsMessage, setOpsMessage] = useState<string | null>(null);
  const [opsMessageTone, setOpsMessageTone] = useState<"info" | "success" | "warning" | "error">("info");
  const [opsBusy, setOpsBusy] = useState(false);
  const [operator, setOperator] = useState("admin");
  const [auditLogs, setAuditLogs] = useState<OperationAuditEntry[]>([]);
  const [isCoolingDown, setIsCoolingDown] = useState(false);
  const [auditPage, setAuditPage] = useState(1);
  const [auditTotal, setAuditTotal] = useState(0);
  const [auditFilterOperator, setAuditFilterOperator] = useState("");
  const [auditFilterOperation, setAuditFilterOperation] = useState("");
  const [auditFilterResult, setAuditFilterResult] = useState("");
  const [auditFromTs, setAuditFromTs] = useState("");
  const [auditToTs, setAuditToTs] = useState("");
  const [redisStats, setRedisStats] = useState<RedisStats | null>(null);

  useEffect(() => {
    let mounted = true;

    async function loadHealth() {
      setLoading(true);
      try {
        const payload = await getSystemQueueHealth();
        if (!mounted) return;
        setHealth(payload);
        setFallbackMode(false);
      } catch {
        if (!mounted) return;
        setHealth(fallback);
        setFallbackMode(true);
      } finally {
        if (mounted) setLoading(false);
      }

      try {
        const redis = await getRedisStats();
        if (!mounted) return;
        setRedisStats(redis);
      } catch {
        if (!mounted) return;
        setRedisStats(null);
      }

      try {
        const logs = await getSystemOperationAuditLogs({
          page: auditPage,
          pageSize: 20,
          operator: auditFilterOperator || undefined,
          operation: auditFilterOperation || undefined,
          result: auditFilterResult || undefined,
          fromTs: auditFromTs || undefined,
          toTs: auditToTs || undefined,
        });
        if (!mounted) return;
        setAuditLogs(logs.items);
        setAuditTotal(logs.total);
      } catch {
        if (!mounted) return;
        setOpsMessage(t("system.auditFiltersFailed"));
        setOpsMessageTone("warning");
      }
    }

    loadHealth();
    const timer = window.setInterval(loadHealth, 5000);

    return () => {
      mounted = false;
      window.clearInterval(timer);
    };
  }, [auditPage, auditFilterOperator, auditFilterOperation, auditFilterResult, auditFromTs, auditToTs, t]);

  function markClientCooldown() {
    setIsCoolingDown(true);
    window.setTimeout(() => {
      setIsCoolingDown(false);
    }, 1500);
  }

  async function handleHealthCheck() {
    if (isCoolingDown) {
      setOpsMessage(t("system.cooldown"));
      setOpsMessageTone("warning");
      return;
    }

    setOpsBusy(true);
    markClientCooldown();
    try {
      const result = await runSystemHealthCheck(operator);
      const workerSummary = Object.entries(result.workers)
        .map(([name, ok]) => `${name}:${ok ? t("system.up") : t("system.down")}`)
        .join(", ");
      setOpsMessage(t("system.healthCheckComplete", {
        redis: result.redis_ok ? t("system.up") : t("system.down"),
        workers: workerSummary,
      }));
      setOpsMessageTone("success");
      const logs = await getSystemOperationAuditLogs({
        page: auditPage,
        pageSize: 20,
        operator: auditFilterOperator || undefined,
        operation: auditFilterOperation || undefined,
        result: auditFilterResult || undefined,
        fromTs: auditFromTs || undefined,
        toTs: auditToTs || undefined,
      });
      setAuditLogs(logs.items);
      setAuditTotal(logs.total);
    } catch {
      setOpsMessage(t("system.healthCheckFailed"));
      setOpsMessageTone("error");
    } finally {
      setOpsBusy(false);
    }
  }

  async function handleSlaScan() {
    if (isCoolingDown) {
      setOpsMessage(t("system.cooldown"));
      setOpsMessageTone("warning");
      return;
    }

    setOpsBusy(true);
    markClientCooldown();
    try {
      const result = await runSlaScan();
      setOpsMessage(t("system.slaScanComplete", {
        scanned: String(result.scanned),
        escalated: String(result.escalated),
        pending: String(result.overdue_pending),
      }));
      setOpsMessageTone("success");
    } catch {
      setOpsMessage(t("system.slaScanFailed"));
      setOpsMessageTone("error");
    } finally {
      setOpsBusy(false);
    }
  }

  async function handlePurgeTopic(topic: string) {
    if (!window.confirm(t("system.confirmPurge", { topic }))) {
      return;
    }
    if (isCoolingDown) {
      setOpsMessage(t("system.cooldown"));
      setOpsMessageTone("warning");
      return;
    }

    setOpsBusy(true);
    markClientCooldown();
    try {
      const result = await purgeQueueTopic(topic, operator);
      setOpsMessage(t("system.topicPurged", { topic: result.topic }));
      setOpsMessageTone("success");
      const refreshed = await getSystemQueueHealth();
      setHealth(refreshed);
      const logs = await getSystemOperationAuditLogs({
        page: auditPage,
        pageSize: 20,
        operator: auditFilterOperator || undefined,
        operation: auditFilterOperation || undefined,
        result: auditFilterResult || undefined,
        fromTs: auditFromTs || undefined,
        toTs: auditToTs || undefined,
      });
      setAuditLogs(logs.items);
      setAuditTotal(logs.total);
      setFallbackMode(false);
    } catch {
      setOpsMessage(t("system.topicPurgeFailed", { topic }));
      setOpsMessageTone("error");
    } finally {
      setOpsBusy(false);
    }
  }

  async function handleRetryDlq(messageId: string) {
    if (!window.confirm(t("system.confirmRetryDlq", { id: messageId }))) {
      return;
    }
    if (isCoolingDown) {
      setOpsMessage(t("system.cooldown"));
      setOpsMessageTone("warning");
      return;
    }

    setOpsBusy(true);
    markClientCooldown();
    try {
      await retryDlqMessage(messageId, operator);
      setOpsMessage(t("system.retryDlqSuccess"));
      setOpsMessageTone("success");
      const refreshed = await getSystemQueueHealth();
      setHealth(refreshed);
      const logs = await getSystemOperationAuditLogs({
        page: auditPage,
        pageSize: 20,
        operator: auditFilterOperator || undefined,
        operation: auditFilterOperation || undefined,
        result: auditFilterResult || undefined,
        fromTs: auditFromTs || undefined,
        toTs: auditToTs || undefined,
      });
      setAuditLogs(logs.items);
      setAuditTotal(logs.total);
      setFallbackMode(false);
    } catch {
      setOpsMessage(t("system.retryDlqFailed"));
      setOpsMessageTone("error");
    } finally {
      setOpsBusy(false);
    }
  }

  const totals = useMemo(() => {
    const queued = health.topics.reduce((sum, item) => sum + item.length, 0);
    const pending = health.topics.reduce((sum, item) => sum + item.pending, 0);
    const lag = health.topics.reduce((sum, item) => sum + item.lag, 0);
    return { queued, pending, lag };
  }, [health]);

  const totalAuditPages = useMemo(() => {
    return Math.max(1, Math.ceil(auditTotal / 20));
  }, [auditTotal]);

  async function applyAuditFilters() {
    setOpsBusy(true);
    try {
      const logs = await getSystemOperationAuditLogs({
        page: 1,
        pageSize: 20,
        operator: auditFilterOperator || undefined,
        operation: auditFilterOperation || undefined,
        result: auditFilterResult || undefined,
        fromTs: auditFromTs || undefined,
        toTs: auditToTs || undefined,
      });
      setAuditPage(1);
      setAuditLogs(logs.items);
      setAuditTotal(logs.total);
      setOpsMessage(t("system.auditFiltersApplied"));
      setOpsMessageTone("success");
    } catch {
      setOpsMessage(t("system.auditFiltersFailed"));
      setOpsMessageTone("error");
    } finally {
      setOpsBusy(false);
    }
  }

  function handleExportCsv() {
    try {
      const url = getSystemOperationAuditCsvUrl({
        operator: auditFilterOperator || undefined,
        operation: auditFilterOperation || undefined,
        result: auditFilterResult || undefined,
        fromTs: auditFromTs || undefined,
        toTs: auditToTs || undefined,
      });
      window.open(url, "_blank", "noopener,noreferrer");
    } catch {
      setOpsMessage(t("system.exportCsvFailed"));
      setOpsMessageTone("error");
    }
  }

  return (
    <section className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">{t("system.title")}</h1>
        <p className="text-sm text-slate-500">{t("system.subtitle")}</p>
      </header>

      {fallbackMode ? (
        <p className="rounded-xl bg-amber-50 px-3 py-2 text-sm text-amber-700">
          {t("system.fallback")}
        </p>
      ) : null}

      {opsMessage ? (
        <p className={`rounded-xl px-3 py-2 text-sm ${toneClasses(opsMessageTone)}`}>{opsMessage}</p>
      ) : null}

      <div className="rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-900">
        <label className="text-xs text-slate-500" htmlFor="operator">{t("system.operator")}</label>
        <input
          id="operator"
          value={operator}
          onChange={(event) => setOperator(event.target.value)}
          className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
          placeholder={t("system.operatorPlaceholder")}
        />
      </div>

      <div className="flex flex-wrap gap-2">
        <button
          onClick={handleHealthCheck}
          disabled={opsBusy}
          className="rounded-lg bg-slate-900 px-3 py-2 text-xs font-medium text-white disabled:opacity-50 dark:bg-slate-700"
        >
          {t("system.runHealthCheck")}
        </button>
        <button
          onClick={handleSlaScan}
          disabled={opsBusy}
          className="rounded-lg border border-slate-300 px-3 py-2 text-xs font-medium text-slate-700 disabled:opacity-50 dark:border-slate-700 dark:text-slate-200"
        >
          {t("system.runSlaScan")}
        </button>
        {health.topics.map((topic) => (
          <button
            key={topic.topic}
            onClick={() => handlePurgeTopic(topic.topic)}
            disabled={opsBusy}
            className="rounded-lg border border-slate-300 px-3 py-2 text-xs font-medium text-slate-700 disabled:opacity-50 dark:border-slate-700 dark:text-slate-200"
          >
            {t("system.purge", { topic: topic.topic })}
          </button>
        ))}
      </div>

      <div className="grid gap-4 rounded-2xl border border-slate-200 bg-white p-4 md:grid-cols-4 dark:border-slate-800 dark:bg-slate-900">
        <MetricCard title={t("system.queuedMessages")} value={totals.queued} tone="text-blue-600" />
        <MetricCard title={t("system.pendingAcks")} value={totals.pending} tone="text-amber-500" />
        <MetricCard title={t("system.consumerLag")} value={totals.lag} tone="text-violet-500" />
        <MetricCard title={t("system.dlqSize")} value={health.dlq_size} tone="text-rose-500" />
        {redisStats && (
          <div className="col-span-2 rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-900">
            <p className="text-xs text-slate-500">{t("system.redis.title")}</p>
            <div className="mt-1 grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
              <span className="text-slate-400">{t("system.redis.version")}</span>
              <span className="font-medium text-slate-700 dark:text-slate-200">{redisStats.redis_version ?? "—"}</span>
              <span className="text-slate-400">{t("system.redis.uptime")}</span>
              <span className="font-medium text-slate-700 dark:text-slate-200">{redisStats.uptime_days ?? "—"}</span>
              <span className="text-slate-400">{t("system.redis.connectedClients")}</span>
              <span className="font-medium text-slate-700 dark:text-slate-200">{redisStats.connected_clients ?? "—"}</span>
              <span className="text-slate-400">{t("system.redis.usedMemory")}</span>
              <span className="font-medium text-slate-700 dark:text-slate-200">{redisStats.used_memory_human ?? "—"}</span>
              <span className="text-slate-400">{t("system.redis.role")}</span>
              <span className="font-medium text-slate-700 dark:text-slate-200">{redisStats.role ?? "—"}</span>
            </div>
          </div>
        )}
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.6fr_1fr]">
        <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
          <header className="border-b border-slate-200 px-4 py-3 text-sm font-semibold dark:border-slate-800">
            {t("system.queueTopics")}
          </header>
          <table className="min-w-full text-left text-sm">
            <thead className="border-b border-slate-200 bg-slate-50 text-slate-500 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-400">
              <tr>
                <th className="px-4 py-3">{t("system.table.topic")}</th>
                <th className="px-4 py-3">{t("system.table.length")}</th>
                <th className="px-4 py-3">{t("system.table.pending")}</th>
                <th className="px-4 py-3">{t("system.table.lag")}</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td className="px-4 py-4 text-slate-500" colSpan={4}>{t("system.loadingQueueMetrics")}</td>
                </tr>
              ) : health.topics.map((topic) => (
                <tr key={topic.topic} className="border-b border-slate-200/70 last:border-none dark:border-slate-800">
                  <td className="px-4 py-3 font-medium">{topic.topic}</td>
                  <td className="px-4 py-3">{topic.length}</td>
                  <td className="px-4 py-3">{topic.pending}</td>
                  <td className="px-4 py-3">{topic.lag}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
          <header className="border-b border-slate-200 px-4 py-3 text-sm font-semibold dark:border-slate-800">
            {t("system.dlqEvents")}
          </header>
          <div className="max-h-[340px] space-y-2 overflow-auto p-4 text-xs">
            {health.dlq_recent.length === 0 ? (
              <p className="text-slate-500">{t("system.noDlq")}</p>
            ) : health.dlq_recent.map((item) => (
              <article key={item.message_id} className="rounded-lg bg-rose-50 p-3 dark:bg-rose-900/20">
                <p className="font-semibold text-rose-700 dark:text-rose-300">{item.task_type} • {item.task_id}</p>
                <p className="mt-1 text-slate-600 dark:text-slate-300">{t("system.table.campaign")}: {item.campaign_id}</p>
                <p className="mt-1 text-slate-600 dark:text-slate-300">{t("system.table.reason")}: {item.reason}</p>
                <button
                  onClick={() => handleRetryDlq(item.message_id)}
                  disabled={opsBusy}
                  className="mt-2 rounded-md bg-rose-600 px-2.5 py-1 text-[11px] font-medium text-white disabled:opacity-50"
                >
                  {t("system.retry")}
                </button>
              </article>
            ))}
          </div>
        </div>
      </div>

      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <header className="border-b border-slate-200 px-4 py-3 text-sm font-semibold dark:border-slate-800">
          {t("system.auditLogs")}
        </header>
        <div className="grid gap-2 border-b border-slate-200 p-3 md:grid-cols-6 dark:border-slate-800">
          <input
            value={auditFilterOperator}
            onChange={(event) => setAuditFilterOperator(event.target.value)}
            placeholder={t("system.filterOperator")}
            className="rounded-lg border border-slate-300 px-2 py-1 text-xs dark:border-slate-700 dark:bg-slate-950"
          />
          <input
            value={auditFilterOperation}
            onChange={(event) => setAuditFilterOperation(event.target.value)}
            placeholder={t("system.filterOperation")}
            className="rounded-lg border border-slate-300 px-2 py-1 text-xs dark:border-slate-700 dark:bg-slate-950"
          />
          <select
            value={auditFilterResult}
            onChange={(event) => setAuditFilterResult(event.target.value)}
            className="rounded-lg border border-slate-300 px-2 py-1 text-xs dark:border-slate-700 dark:bg-slate-950"
          >
            <option value="">{t("system.allResults")}</option>
            <option value="ok">{t("system.result.ok")}</option>
            <option value="failed">{t("system.result.failed")}</option>
            <option value="rate_limited">{t("system.result.rateLimited")}</option>
          </select>
          <input
            value={auditFromTs}
            onChange={(event) => setAuditFromTs(event.target.value)}
            placeholder={t("system.fromIso")}
            className="rounded-lg border border-slate-300 px-2 py-1 text-xs dark:border-slate-700 dark:bg-slate-950"
          />
          <input
            value={auditToTs}
            onChange={(event) => setAuditToTs(event.target.value)}
            placeholder={t("system.toIso")}
            className="rounded-lg border border-slate-300 px-2 py-1 text-xs dark:border-slate-700 dark:bg-slate-950"
          />
          <button
            onClick={applyAuditFilters}
            disabled={opsBusy}
            className="rounded-lg bg-slate-900 px-2 py-1 text-xs font-medium text-white disabled:opacity-50 dark:bg-slate-700"
          >
            {t("system.apply")}
          </button>
          <button
            onClick={handleExportCsv}
            disabled={opsBusy}
            className="rounded-lg border border-slate-300 px-2 py-1 text-xs font-medium text-slate-700 disabled:opacity-50 dark:border-slate-700 dark:text-slate-200"
          >
            {t("system.exportCsv")}
          </button>
        </div>
        <div className="max-h-[280px] overflow-auto">
          <table className="min-w-full text-left text-xs">
            <thead className="border-b border-slate-200 bg-slate-50 text-slate-500 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-400">
              <tr>
                <th className="px-4 py-2">{t("system.table.time")}</th>
                <th className="px-4 py-2">{t("system.operator")}</th>
                <th className="px-4 py-2">{t("system.table.operation")}</th>
                <th className="px-4 py-2">{t("system.table.target")}</th>
                <th className="px-4 py-2">{t("system.table.result")}</th>
              </tr>
            </thead>
            <tbody>
              {auditLogs.length === 0 ? (
                <tr>
                  <td className="px-4 py-3 text-slate-500" colSpan={5}>{t("system.noAudit")}</td>
                </tr>
              ) : auditLogs.map((log) => (
                <tr key={`${log.timestamp}-${log.operation}-${log.target}`} className="border-b border-slate-200/70 last:border-none dark:border-slate-800">
                  <td className="px-4 py-2">{formatDateTime(locale, log.timestamp)}</td>
                  <td className="px-4 py-2">{log.operator}</td>
                  <td className="px-4 py-2">{translateOperationToken(log.operation, t)}</td>
                  <td className="px-4 py-2">{log.target}</td>
                  <td className="px-4 py-2">
                    <span className={`rounded-full px-2 py-0.5 ${resultBadgeClasses(log.result)}`}>
                      {translateResultToken(log.result, t)}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="flex items-center justify-between border-t border-slate-200 px-4 py-2 text-xs dark:border-slate-800">
          <span>{t("system.page", { page: auditPage, total: totalAuditPages })}</span>
          <div className="space-x-2">
            <button
              disabled={auditPage <= 1 || opsBusy}
              onClick={() => setAuditPage((prev) => Math.max(1, prev - 1))}
              className="rounded border border-slate-300 px-2 py-1 disabled:opacity-50 dark:border-slate-700"
            >
              {t("system.prev")}
            </button>
            <button
              disabled={auditPage >= totalAuditPages || opsBusy}
              onClick={() => setAuditPage((prev) => Math.min(totalAuditPages, prev + 1))}
              className="rounded border border-slate-300 px-2 py-1 disabled:opacity-50 dark:border-slate-700"
            >
              {t("system.next")}
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}

function MetricCard({ title, value, tone }: { title: string; value: number; tone: string }) {
  return (
    <div>
      <p className="text-xs text-slate-500">{title}</p>
      <p className={`text-2xl font-semibold ${tone}`}>{value}</p>
    </div>
  );
}

function translateResultToken(
  token: string,
  t: TranslateFunction,
) {
  if (token === "ok") return t("system.result.ok");
  if (token === "failed") return t("system.result.failed");
  if (token === "rate_limited") return t("system.result.rateLimited");
  return token;
}

function translateOperationToken(
  token: string,
  t: TranslateFunction,
) {
  if (token === "health_check") return t("system.operation.healthCheck");
  if (token === "purge_topic") return t("system.operation.purgeTopic");
  if (token === "retry_dlq") return t("system.operation.retryDlq");
  return token;
}

function toneClasses(tone: "info" | "success" | "warning" | "error") {
  if (tone === "success") return "bg-emerald-50 text-emerald-700";
  if (tone === "warning") return "bg-amber-50 text-amber-700";
  if (tone === "error") return "bg-rose-50 text-rose-700";
  return "bg-blue-50 text-blue-700";
}

function resultBadgeClasses(token: string) {
  if (token === "ok") return "bg-emerald-100 text-emerald-700";
  if (token === "failed") return "bg-rose-100 text-rose-700";
  if (token === "rate_limited") return "bg-amber-100 text-amber-700";
  return "bg-slate-100 text-slate-700";
}

function statusBadgeClasses(status: string) {
  if (status === "open") return "bg-blue-100 text-blue-700";
  if (status === "in_progress") return "bg-indigo-100 text-indigo-700";
  if (status === "review_pending") return "bg-amber-100 text-amber-700";
  if (status === "approved") return "bg-emerald-100 text-emerald-700";
  if (status === "rejected") return "bg-rose-100 text-rose-700";
  if (status === "done") return "bg-slate-100 text-slate-500";
  if (status === "cancelled") return "bg-slate-100 text-slate-400";
  if (status === "blocked") return "bg-orange-100 text-orange-700";
  return "bg-slate-100 text-slate-700";
}
