"use client";

import { Area, AreaChart, CartesianGrid, Tooltip, XAxis, YAxis } from "recharts";
import { useI18n } from "@/lib/i18n/context";

type TrendPoint = {
  label: string;
  tasks: number;
};

export function KpiOverview({ trend }: { trend?: TrendPoint[] }) {
  const { t } = useI18n();
  const trendData = trend ?? [];

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-200">{t("dashboard.throughputTitle")}</h3>
      <p className="mb-3 text-xs text-slate-500">{t("dashboard.throughputSubtitle")}</p>

      {trendData.length === 0 ? (
        <p className="rounded-xl bg-slate-50 px-3 py-2 text-xs text-slate-500 dark:bg-slate-950 dark:text-slate-400">
          {t("dashboard.noTrendData")}
        </p>
      ) : (
        <div className="overflow-x-auto">
          <AreaChart width={760} height={280} data={trendData}>
            <defs>
              <linearGradient id="kpiGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#0071E3" stopOpacity={0.45} />
                <stop offset="95%" stopColor="#0071E3" stopOpacity={0.06} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#CBD5E1" opacity={0.35} />
            <XAxis dataKey="label" tick={{ fontSize: 12 }} />
            <YAxis tick={{ fontSize: 12 }} />
            <Tooltip />
            <Area dataKey="tasks" stroke="#0071E3" fill="url(#kpiGradient)" strokeWidth={2} />
          </AreaChart>
        </div>
      )}
    </div>
  );
}
