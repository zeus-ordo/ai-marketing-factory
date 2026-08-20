"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { listCampaigns, listCampaignTasks, type CampaignTask } from "@/lib/api/campaigns";
import { useI18n, type TranslateFunction } from "@/lib/i18n/context";
import type { TranslationKey } from "@/lib/i18n/translations";

const edges: Edge[] = [
  { id: "a-b", source: "scheduler", target: "copywriting", animated: true },
  { id: "b-c", source: "copywriting", target: "image_generation", animated: true },
  { id: "c-d", source: "image_generation", target: "video_generation", animated: true },
  { id: "c-e", source: "image_generation", target: "ads_strategy", animated: true },
  { id: "d-f", source: "video_generation", target: "validation", animated: true },
  { id: "e-f", source: "ads_strategy", target: "validation", animated: true },
];

function logClass(level: string) {
  if (level === "SYS") return "text-violet-400";
  if (level === "WORKER") return "text-emerald-400";
  return "text-sky-400";
}

export function WorkflowBoard() {
  const { t, locale } = useI18n();
  const logContainerRef = useRef<HTMLDivElement | null>(null);
  const baseNodes = useMemo<Node[]>(() => {
    return [
      {
        id: "scheduler",
        position: { x: 30, y: 120 },
        data: { label: `${t("workflow.scheduler")}\n${t("status.planned")}` },
        type: "input",
      },
      {
        id: "copywriting",
        position: { x: 280, y: 20 },
        data: { label: `${t("workflow.copyWorker")}\n${t("status.pending")}` },
      },
      {
        id: "image_generation",
        position: { x: 280, y: 150 },
        data: { label: `${t("workflow.imageWorker")}\n${t("status.pending")}` },
      },
      {
        id: "video_generation",
        position: { x: 520, y: 20 },
        data: { label: `${t("workflow.videoWorker")}\n${t("status.pending")}` },
      },
      {
        id: "ads_strategy",
        position: { x: 520, y: 220 },
        data: { label: `${t("workflow.adsStrategy")}\n${t("status.pending")}` },
      },
      {
        id: "validation",
        position: { x: 760, y: 120 },
        data: { label: `${t("workflow.validation")}\n${t("status.waiting")}` },
        type: "output",
      },
    ];
  }, [t]);

  const [nodes, setNodes] = useState<Node[]>(baseNodes);
  const [logs, setLogs] = useState<Array<{ level: string; message: string }>>([
    { level: "SYS", message: t("workflow.waitingData") },
  ]);

  useEffect(() => {
    const el = logContainerRef.current;
    if (!el) return;

    el.scrollTop = el.scrollHeight;
  }, [logs]);

  useEffect(() => {
    let mounted = true;

    async function loadWorkflow() {
      try {
        const campaigns = await listCampaigns();
        const activeCampaign = campaigns.find((item) => item.status === "running") ?? campaigns[0];

        if (!activeCampaign) {
          if (!mounted) return;
          setLogs([{ level: "SYS", message: t("workflow.noCampaign") }]);
          return;
        }

        const tasks = await listCampaignTasks(activeCampaign.campaign_id);
        if (!mounted) return;

        setNodes(createNodes(tasks, t));
        setLogs(createLogs(activeCampaign.campaign_id, tasks, t));
      } catch {
        if (!mounted) return;
        setLogs([{ level: "SYS", message: t("workflow.apiUnavailable") }]);
      }
    }

    loadWorkflow();
    return () => {
      mounted = false;
    };
  }, [t]);

  const fitViewOptions = useMemo(() => ({ padding: 0.25 }), []);

  return (
    <div className="grid gap-4 xl:grid-cols-[1.7fr_1fr]">
      <div className="h-[540px] overflow-hidden rounded-2xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
        <ReactFlow key={locale} nodes={nodes} edges={edges} fitView fitViewOptions={fitViewOptions}>
          <MiniMap pannable zoomable />
          <Controls />
          <Background gap={16} size={1} />
        </ReactFlow>
      </div>

      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-slate-950 text-xs text-slate-100 dark:border-slate-800">
        <header className="border-b border-slate-800 px-4 py-3 text-sm font-semibold">{t("workflow.executionLog")}</header>
        <div ref={logContainerRef} className="h-[500px] space-y-2 overflow-auto px-4 py-3 font-mono">
          {logs.map((item, index) => (
            <p key={`${item.level}-${index}`}>
              <span className={logClass(item.level)}>[{item.level}]</span> {item.message}
            </p>
          ))}
        </div>
      </div>
    </div>
  );
}

function createNodes(tasks: CampaignTask[], t: TranslateFunction): Node[] {
  const baseNodes: Node[] = [
    {
      id: "scheduler",
      position: { x: 30, y: 120 },
      data: { label: `${t("workflow.scheduler")}\n${t("status.planned")}` },
      type: "input",
    },
    {
      id: "copywriting",
      position: { x: 280, y: 20 },
      data: { label: `${t("workflow.copyWorker")}\n${t("status.pending")}` },
    },
    {
      id: "image_generation",
      position: { x: 280, y: 150 },
      data: { label: `${t("workflow.imageWorker")}\n${t("status.pending")}` },
    },
    {
      id: "video_generation",
      position: { x: 520, y: 20 },
      data: { label: `${t("workflow.videoWorker")}\n${t("status.pending")}` },
    },
    {
      id: "ads_strategy",
      position: { x: 520, y: 220 },
      data: { label: `${t("workflow.adsStrategy")}\n${t("status.pending")}` },
    },
    {
      id: "validation",
      position: { x: 760, y: 120 },
      data: { label: `${t("workflow.validation")}\n${t("status.waiting")}` },
      type: "output",
    },
  ];

  const taskByType = new Map(tasks.map((task) => [task.task_type, task]));

  return baseNodes.map((node) => {
    if (node.id === "scheduler") {
      return { ...node, data: { label: `${t("workflow.scheduler")}\n${t("status.running")}` } };
    }

    if (node.id === "validation") {
      const allDone = tasks.length > 0 && tasks.every((task) => task.status === "passed");
      return {
        ...node,
        data: { label: `${t("workflow.validation")}\n${allDone ? t("status.passed") : t("status.waiting")}` },
      };
    }

    const task = taskByType.get(node.id as CampaignTask["task_type"]);
    if (!task) return node;

    const title = taskTypeLabel(node.id as CampaignTask["task_type"], t);

    return {
        ...node,
        data: {
          label: `${title}\n${t(taskStatusKey(task.status))}`,
        },
      };
  });
}

function createLogs(
  campaignId: string,
  tasks: CampaignTask[],
  t: TranslateFunction,
): Array<{ level: string; message: string }> {
  const taskLogs = tasks.map((task) => ({
    level: task.status === "failed" ? "SYS" : "WORKER",
    message: `${taskTypeLabel(task.task_type, t)} -> ${t(taskStatusKey(task.status))} (${t("workflow.priority")} ${task.priority})`,
  }));

  return [
    { level: "INFO", message: t("workflow.campaignLoaded", { id: campaignId }) },
    ...taskLogs,
  ];
}

function taskTypeLabel(
  taskType: CampaignTask["task_type"],
  t: TranslateFunction,
) {
  if (taskType === "copywriting") return t("workflow.copyWorker");
  if (taskType === "image_generation") return t("workflow.imageWorker");
  if (taskType === "video_generation") return t("workflow.videoWorker");
  if (taskType === "ads_strategy") return t("workflow.adsStrategy");
  return taskType;
}

function taskStatusKey(status: CampaignTask["status"]): TranslationKey {
  if (status === "pending") return "status.pending";
  if (status === "planned") return "status.planned";
  if (status === "running") return "status.running";
  if (status === "validating") return "status.validating";
  if (status === "passed") return "status.passed";
  if (status === "retrying") return "status.retrying";
  return "status.failed";
}
