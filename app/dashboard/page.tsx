"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { KpiOverview } from "@/components/dashboard/kpi-overview";
import { getSystemQueueHealth, listCampaigns, listReviewQueue, type QueueHealthResponse, type ReviewQueueResponse } from "@/lib/api/campaigns";
import { useI18n } from "@/lib/i18n/context";
import { formatDateTime } from "@/lib/i18n/format";

type TrendPoint = {
  label: string;
  tasks: number;
};

type RunningItem = {
  task: string;
  progress: number;
};

export default function DashboardPage() {
  const { t, locale } = useI18n();
  const [summary, setSummary] = useState<Array<{ label: string; value: string; tone: string }>>([]);
  const [runningNow, setRunningNow] = useState<RunningItem[]>([]);
  const [actionRequired, setActionRequired] = useState<string[]>([]);
  const [trend, setTrend] = useState<TrendPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);

  const fetchDashboard = useCallback(async () => {
    setMessage(null);
    try {
      const campaigns = await listCampaigns();
      const [queueHealth, reviewQueue] = await Promise.all([
        safeFetch(getSystemQueueHealth, emptyQueueHealth),
        safeFetch(() => listReviewQueue({ page: 1, pageSize: 1, status: "review_pending" }), emptyReviewQueue),
      ]);

      const activeCampaigns = campaigns.filter((item) => item.status === "running" || item.status === "draft").length;
      const failedCampaigns = campaigns.filter((item) => item.status === "failed").length;
      const activeQueueTopics = queueHealth.topics.filter((topic) => topic.pending > 0 || topic.length > 0 || topic.lag > 0);
      const runningWorkers = activeQueueTopics.length;
      const actionRequiredCount = failedCampaigns + queueHealth.dlq_size + reviewQueue.total;

      setSummary([
        { label: t("dashboard.activeCampaigns"), value: String(activeCampaigns), tone: "text-blue-600" },
        { label: t("dashboard.runningWorkers"), value: String(runningWorkers), tone: "text-emerald-500" },
        { label: t("dashboard.actionRequired"), value: String(actionRequiredCount), tone: "text-amber-500" },
        { label: t("dashboard.failedJobs"), value: String(failedCampaigns), tone: "text-rose-500" },
      ]);

      const liveRunning = activeQueueTopics.slice(0, 3).map((topic) => ({
        task: `${topic.topic} · pending ${topic.pending}`,
        progress: progressByQueueTopic(topic),
      }));
      setRunningNow(liveRunning);

      const alerts: string[] = [];
      if (failedCampaigns > 0) {
        alerts.push(t("dashboard.failedTasksAlert", { count: failedCampaigns }));
      }
      if (queueHealth.dlq_size > 0) {
        alerts.push(t("dashboard.dlqAlert", { count: queueHealth.dlq_size }));
      }
      if (reviewQueue.total > 0) {
        alerts.push(t("dashboard.reviewAlert", { count: reviewQueue.total }));
      }
      if (alerts.length === 0) {
        alerts.push(t("dashboard.noActionRequired"));
      }
      setActionRequired(alerts.slice(0, 3));

      const completedNow = campaigns.filter((item) => item.status === "completed").length;
      const timestamp = new Date();
      const label = timestamp.toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit" });
      setTrend((prev) => {
        const next = [...prev, { label, tasks: completedNow }];
        return next.slice(-7);
      });

      setLastUpdated(timestamp.toISOString());
    } catch {
      setMessage(t("dashboard.liveUnavailable"));
    } finally {
      setLoading(false);
    }
  }, [locale, t]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void fetchDashboard();
    }, 0);

    const interval = window.setInterval(() => {
      void fetchDashboard();
    }, 8000);

    return () => {
      window.clearTimeout(timer);
      window.clearInterval(interval);
    };
  }, [fetchDashboard]);

  const lastUpdatedLabel = useMemo(() => {
    if (!lastUpdated) return t("dashboard.waitingUpdate");
    return t("dashboard.lastUpdated", { time: formatDateTime(locale, lastUpdated) });
  }, [lastUpdated, locale, t]);

  return (
    <section className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">{t("dashboard.title")}</h1>
        <p className="text-sm text-slate-500">{t("dashboard.subtitle")}</p>
        <p className="mt-1 text-xs text-slate-400">{lastUpdatedLabel}</p>
      </header>

      {message ? <p className="rounded-xl bg-amber-50 px-3 py-2 text-sm text-amber-700">{message}</p> : null}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {summary.map((item) => (
          <article key={item.label} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
            <p className="text-sm text-slate-500">{item.label}</p>
            <p className={`mt-2 text-3xl font-semibold ${item.tone}`}>{item.value}</p>
          </article>
        ))}
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.7fr_1fr]">
        <KpiOverview trend={trend} />

        <div className="space-y-4">
          <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
            <h3 className="text-sm font-semibold">{t("dashboard.runningNow")}</h3>
            <div className="mt-3 space-y-3">
              {loading ? (
                <p className="text-xs text-slate-500">{t("common.loading")}</p>
              ) : runningNow.length === 0 ? (
                <p className="text-xs text-slate-500">{t("dashboard.noRunningTasks")}</p>
              ) : runningNow.map((job) => (
                <div key={job.task}>
                  <div className="mb-1 flex items-center justify-between text-xs">
                    <span>{job.task}</span>
                    <span>{job.progress}%</span>
                  </div>
                  <div className="h-2 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800">
                    <div className="h-full bg-blue-600" style={{ width: `${job.progress}%` }} />
                  </div>
                </div>
              ))}
            </div>
          </section>

          <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
            <h3 className="text-sm font-semibold">{t("dashboard.actionRequiredPanel")}</h3>
            <ul className="mt-3 space-y-2 text-sm text-slate-600 dark:text-slate-300">
              {actionRequired.map((item) => (
                <li key={item} className="rounded-lg bg-amber-50 px-3 py-2 dark:bg-amber-900/20">
                  {item}
                </li>
              ))}
            </ul>
          </section>
        </div>
      </div>
    </section>
  );
}

async function safeFetch<T>(loader: () => Promise<T>, fallback: T): Promise<T> {
  try {
    return await loader();
  } catch {
    return fallback;
  }
}

const emptyQueueHealth: QueueHealthResponse = {
  topics: [],
  dlq_size: 0,
  dlq_recent: [],
};

const emptyReviewQueue: ReviewQueueResponse = {
  items: [],
  total: 0,
};

function progressByQueueTopic(topic: QueueHealthResponse["topics"][number]) {
  const total = Math.max(1, topic.length + topic.pending + topic.lag);
  const completedRatio = Math.max(0, Math.min(1, 1 - topic.pending / total));
  return Math.max(10, Math.min(95, Math.round(completedRatio * 100)));
}
