export type CampaignStatus = "draft" | "running" | "completed" | "failed";

export type CampaignTask = {
  company_id: string;
  task_id: string;
  campaign_id: string;
  task_type: "copywriting" | "image_generation" | "video_generation" | "ads_strategy";
  status: "pending" | "planned" | "running" | "validating" | "passed" | "failed" | "retrying";
  priority: number;
  depends_on: string[];
  acceptance: string[];
};

export type CampaignBrief = {
  campaign_name: string;
  product_name: string;
  description?: string;
  objective: string;
  language?: string;
  industry_category?: string;
  project_description?: string;
  target_audience: {
    age_range: string;
    gender: string;
    persona: string;
  };
  platforms: string[];
  budget: number;
  brand_tone: string[];
  deliverables: {
    copy_variants: number;
    image_assets: number;
    short_video_assets: number;
    ads_strategy?: number;
  };
  mandatory_elements: string[];
  forbidden_elements: string[];
  deadline: string;
};

export type CampaignRecord = {
  company_id: string;
  campaign_id: string;
  status: CampaignStatus;
  created_at: string;
  brief: CampaignBrief;
};

export type ValidationResultRecord = {
  company_id: string;
  validation_id: string;
  campaign_id: string;
  asset_id: string;
  validator: string;
  score: number;
  result: "passed" | "failed";
  reasons: string[];
  created_at: string;
  run_id?: string;
};

export type FinalAssetBundle = {
  campaign_id: string;
  status: string;
  copy_assets: Array<{ variant_id: string; asset_name?: string | null; text: string }>;
  image_assets: Array<{ asset_id: string; asset_name?: string | null; url: string; validated: boolean; score?: number }>;
  video_assets: Array<{ asset_id: string; asset_name?: string | null; url: string; validated: boolean; score?: number }>;
  ads_strategy: Record<string, { budget: number }>;
};

export type QueueTopicHealth = {
  topic: string;
  length: number;
  pending: number;
  lag: number;
};

export type DlqItem = {
  message_id: string;
  campaign_id: string;
  task_id: string;
  task_type: string;
  reason: string;
};

export type QueueHealthResponse = {
  topics: QueueTopicHealth[];
  dlq_size: number;
  dlq_recent: DlqItem[];
};

export type SystemTraceHealth = {
  retention_days: number;
  cleanup_interval_hours: number;
  last_cleanup_at?: string;
  trace_total: number;
  event_total: number;
  chat_total: number;
  work_order_total: number;
  work_order_message_total: number;
  work_order_overdue_total: number;
  work_order_escalated_total: number;
  latest_event_at?: string;
  latest_chat_at?: string;
  top_event_types: Array<{ event_type: string; total: number }>;
};

export type OperationHealthCheckResponse = {
  redis_ok: boolean;
  workers: Record<string, boolean>;
};

export type SlaScanResponse = {
  scanned: number;
  escalated: number;
  overdue_pending: number;
};

export type PurgeTopicResponse = {
  topic: string;
  purged: boolean;
};

export type RetryDlqResponse = {
  message_id: string;
  retried: boolean;
  detail: string;
};

export type OperationAuditEntry = {
  timestamp: string;
  operator: string;
  operation: string;
  target: string;
  result: string;
  detail: string;
};

export type OperationAuditResponse = {
  items: OperationAuditEntry[];
  total: number;
  page: number;
  page_size: number;
};

type CampaignListResponse = {
  items: CampaignRecord[];
  total: number;
};

type CampaignTasksResponse = {
  campaign_id: string;
  tasks: CampaignTask[];
};

type ValidationListResponse = {
  campaign_id: string;
  items: ValidationResultRecord[];
  total: number;
};

type CampaignCreatedResponse = {
  campaign_id: string;
  company_id: string;
  status: string;
};

type CampaignDeleteResponse = {
  campaign_id: string;
  deleted: boolean;
};

export type ManualAssetCreateResponse = {
  campaign_id: string;
  asset_id: string;
  asset_type: "image" | "video";
  validation_status: string;
};

type CampaignRunResponse = {
  campaign_id: string;
  status: string;
  message: string;
  run_id?: string;
  run_number?: number;
};

export type CampaignRunSummary = {
  run_id: string;
  campaign_id: string;
  run_number: number;
  status: string;
  started_at: string;
  completed_at?: string;
  triggered_by: string;
  metadata_json: Record<string, unknown>;
};

export type CampaignRunListResponse = {
  campaign_id: string;
  runs: CampaignRunSummary[];
  total: number;
};

export type AssetVersion = {
  version_id: string;
  asset_id: string;
  run_id: string;
  version_number: number;
  url: string;
  metadata_json: Record<string, unknown>;
  created_at: string;
};

export type AssetVersionListResponse = {
  asset_id: string;
  versions: AssetVersion[];
  total: number;
};

export type CampaignReferenceRecord = {
  reference_id: string;
  campaign_id: string;
  file_name: string;
  file_type: string;
  file_size: number;
  uploaded_at: string;
  download_url: string;
  folder?: string | null;
  metadata?: Record<string, unknown>;
};

export type KnowledgeItemRecord = {
  item_id: string;
  company_id: string;
  title: string;
  source: "ai" | "manual";
  description: string;
  content_url: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
};

type KnowledgeItemListResponse = {
  items: KnowledgeItemRecord[];
  total: number;
};

export type CampaignTraceSummary = {
  trace: {
    company_id: string;
    trace_id: string;
    campaign_id: string;
    created_by: string;
    source: string;
    created_at: string;
    updated_at: string;
  } | null;
  event_total: number;
  chat_total: number;
};

export type CampaignTraceEvent = {
  company_id: string;
  event_id: string;
  trace_id: string;
  campaign_id: string;
  event_type: string;
  actor_id: string;
  actor_role: string;
  summary: string;
  payload: Record<string, unknown>;
  created_at: string;
};

export type CampaignTraceChatMessage = {
  company_id: string;
  message_id: string;
  trace_id: string;
  campaign_id: string;
  role: string;
  content_masked: string;
  raw_ref?: string;
  created_at: string;
};

export type WorkOrderStatus =
  | "open"
  | "in_progress"
  | "blocked"
  | "review_pending"
  | "approved"
  | "rejected"
  | "done"
  | "cancelled";

export type WorkOrderRecord = {
  company_id: string;
  work_order_id: string;
  campaign_id: string;
  task_id?: string;
  title: string;
  description: string;
  assignee?: string;
  status: WorkOrderStatus;
  priority: number;
  created_by: string;
  due_at?: string;
  escalated_at?: string;
  escalation_reason?: string;
  overdue: boolean;
  created_at: string;
  updated_at: string;
};

export type WorkOrderMessageRecord = {
  company_id: string;
  message_id: string;
  work_order_id: string;
  campaign_id: string;
  role: string;
  content_masked: string;
  actor_id: string;
  created_at: string;
};

type CampaignReferenceListResponse = {
  items: CampaignReferenceRecord[];
  total: number;
};

type CampaignTraceEventListResponse = {
  items: CampaignTraceEvent[];
  total: number;
  next_cursor?: string;
};

type CampaignTraceChatListResponse = {
  items: CampaignTraceChatMessage[];
  total: number;
  next_cursor?: string;
};

type WorkOrderMessageListResponse = {
  items: WorkOrderMessageRecord[];
  total: number;
  next_cursor?: string;
};

function getApiBase(): string | null {
  const base = process.env.NEXT_PUBLIC_CAMPAIGN_API_BASE ?? process.env.NEXT_PUBLIC_API_BASE;
  if (!base) return null;
  if (base === "/") {
    return typeof window === "undefined" ? (process.env.CAMPAIGN_API_BASE ?? "http://campaign-service:8080") : "/";
  }
  return base.replace(/\/$/, "");
}

function buildApiUrl(apiBase: string, path: string): string {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  if (apiBase === "/") return normalizedPath;
  return `${apiBase}${normalizedPath}`;
}

function getMembershipApiBase(): string {
  const base = process.env.NEXT_PUBLIC_MEMBERSHIP_API_BASE ?? "/";
  if (!base || base === "/") return "/";
  return base.replace(/\/$/, "");
}

let refreshAccessTokenPromise: Promise<boolean> | null = null;

async function refreshAccessTokenOnce(): Promise<boolean> {
  if (typeof window === "undefined") return false;
  if (refreshAccessTokenPromise) return refreshAccessTokenPromise;
  refreshAccessTokenPromise = refreshAccessTokenInner().finally(() => {
    refreshAccessTokenPromise = null;
  });
  return refreshAccessTokenPromise;
}

async function refreshAccessTokenInner(): Promise<boolean> {
  const refreshToken = localStorage.getItem("refresh_token");
  if (!refreshToken) return false;
  const membershipBase = getMembershipApiBase();
  const response = await fetch(buildApiUrl(membershipBase, "/api/v1/auth/refresh"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  if (!response.ok) return false;
  const payload = (await response.json()) as { access_token?: string; refresh_token?: string };
  if (!payload.access_token || !payload.refresh_token) return false;
  localStorage.setItem("access_token", payload.access_token);
  localStorage.setItem("refresh_token", payload.refresh_token);
  return true;
}

function getAccessToken(): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem("access_token") ?? "";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const apiBase = getApiBase();
  if (!apiBase) {
    throw new Error("NEXT_PUBLIC_CAMPAIGN_API_BASE is not configured");
  }

  const token = getAccessToken();
  const isFormData = typeof FormData !== "undefined" && init?.body instanceof FormData;
  const existingHeaders = (init?.headers ?? {}) as Record<string, string>;
  const headers: Record<string, string> = isFormData
    ? existingHeaders
    : {
        "Content-Type": "application/json",
        ...existingHeaders,
      };

  // Attach JWT token if available
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  let response = await fetch(buildApiUrl(apiBase, path), {
    ...init,
    headers,
  });

  // Handle 401: redirect to login
  if (response.status === 401) {
    const refreshed = await refreshAccessTokenOnce();
    if (refreshed) {
      const retryHeaders = { ...headers, Authorization: `Bearer ${getAccessToken()}` };
      response = await fetch(buildApiUrl(apiBase, path), {
        ...init,
        headers: retryHeaders,
      });
      if (response.status !== 401) {
        if (!response.ok) {
          const contentType = response.headers.get("content-type") ?? "";
          let message = `Request failed: ${response.status}`;
          if (contentType.includes("application/json")) {
            const payload = (await response.json()) as { detail?: unknown };
            if (typeof payload.detail === "string" && payload.detail.trim()) message = payload.detail;
          } else {
            const errorText = await response.text();
            if (errorText.trim()) message = errorText;
          }
          throw new Error(message);
        }
        return (await response.json()) as T;
      }
    }
    if (typeof window !== "undefined") {
      localStorage.removeItem("access_token");
      localStorage.removeItem("refresh_token");
      window.location.href = "/auth/login";
    }
    throw new Error("Unauthorized");
  }

  if (!response.ok) {
    const contentType = response.headers.get("content-type") ?? "";
    let message = `Request failed: ${response.status}`;

    if (contentType.includes("application/json")) {
      const payload = (await response.json()) as { detail?: unknown };
      if (typeof payload.detail === "string" && payload.detail.trim()) {
        message = payload.detail;
      }
    } else {
      const errorText = await response.text();
      if (errorText.trim()) {
        message = errorText;
      }
    }

    throw new Error(message);
  }

  return (await response.json()) as T;
}

export async function listCampaigns(): Promise<CampaignRecord[]> {
  const data = await request<CampaignListResponse>("/api/v1/campaigns");
  return data.items;
}

export async function getCampaign(campaignId: string): Promise<CampaignRecord> {
  return request<CampaignRecord>(`/api/v1/campaigns/${campaignId}`);
}

export async function createCampaign(brief: CampaignBrief): Promise<CampaignCreatedResponse> {
  return request<CampaignCreatedResponse>("/api/v1/campaigns", {
    method: "POST",
    body: JSON.stringify(brief),
  });
}

export async function updateCampaign(campaignId: string, brief: CampaignBrief): Promise<CampaignRecord> {
  return request<CampaignRecord>(`/api/v1/campaigns/${campaignId}`, {
    method: "PATCH",
    body: JSON.stringify(brief),
  });
}

export async function deleteCampaign(campaignId: string): Promise<CampaignDeleteResponse> {
  return request<CampaignDeleteResponse>(`/api/v1/campaigns/${campaignId}`, {
    method: "DELETE",
  });
}

export async function runCampaign(campaignId: string): Promise<CampaignRunResponse> {
  return request<CampaignRunResponse>(`/api/v1/campaigns/${campaignId}/run`, {
    method: "POST",
  });
}

export async function listCampaignRuns(campaignId: string): Promise<CampaignRunSummary[]> {
  const data = await request<CampaignRunListResponse>(`/api/v1/campaigns/${campaignId}/runs`);
  return data.runs;
}

export async function listAssetVersions(assetId: string): Promise<AssetVersion[]> {
  const data = await request<AssetVersionListResponse>(`/api/v1/assets/${assetId}/versions`);
  return data.versions;
}

export async function regenerateAsset(
  assetId: string,
  payload?: { reject_reason?: string; user_instruction?: string; operator?: string },
): Promise<{ status: string; asset_id: string }> {
  const data = await request<{ status: string; asset_id: string; asset_name?: string }>(`/api/v1/assets/${assetId}/regenerate`, {
    method: "POST",
    body: JSON.stringify(payload ?? {}),
  });
  return data;
}

export async function listCampaignTasks(campaignId: string): Promise<CampaignTask[]> {
  const data = await request<CampaignTasksResponse>(`/api/v1/campaigns/${campaignId}/tasks`);
  return data.tasks;
}

export async function listValidationResults(campaignId: string): Promise<ValidationResultRecord[]> {
  const data = await request<ValidationListResponse>(`/api/v1/campaigns/${campaignId}/validation-results`);
  return data.items;
}

export async function getCampaignBundle(campaignId: string): Promise<FinalAssetBundle> {
  return request<FinalAssetBundle>(`/api/v1/campaigns/${campaignId}/bundle`);
}

export async function uploadManualAsset(params: {
  campaignId: string;
  assetType: "copy" | "image" | "video";
  file: File;
  prompt?: string;
}): Promise<ManualAssetCreateResponse> {
  const formData = new FormData();
  formData.append("asset_type", params.assetType);
  formData.append("file", params.file);
  if (params.prompt) formData.append("prompt", params.prompt);

  return request<ManualAssetCreateResponse>(`/api/v1/campaigns/${params.campaignId}/assets/manual-upload`, {
    method: "POST",
    body: formData,
  });
}

export async function generateSingleAsset(params: {
  campaignId: string;
  assetType: "copy" | "image" | "video";
  prompt?: string;
}): Promise<{ campaign_id: string; asset_type: "copy" | "image" | "video"; status: "queued" }> {
  return request(`/api/v1/campaigns/${params.campaignId}/assets/generate`, {
    method: "POST",
    body: JSON.stringify({ asset_type: params.assetType, prompt: params.prompt ?? "" }),
  });
}

export async function getSystemQueueHealth(): Promise<QueueHealthResponse> {
  return request<QueueHealthResponse>("/api/v1/system/queue-health");
}

export async function getSystemTraceHealth(): Promise<SystemTraceHealth> {
  const response = await fetch("/api/system/trace/health", { cache: "no-store" });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }
  return (await response.json()) as SystemTraceHealth;
}

export async function runSystemHealthCheck(operator?: string): Promise<OperationHealthCheckResponse> {
  return request<OperationHealthCheckResponse>("/api/v1/system/operations/health-check", {
    method: "POST",
    body: JSON.stringify({ operator }),
  });
}

export async function runSlaScan(): Promise<SlaScanResponse> {
  const response = await fetch("/api/system/operations/scan-sla", {
    method: "POST",
    cache: "no-store",
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }
  return (await response.json()) as SlaScanResponse;
}

export interface SlaBacklogEntry {
  work_order_id: string;
  campaign_id: string;
  title: string;
  status: string;
  priority: number;
  due_at: string | null;
  overdue: boolean;
  escalated_at: string | null;
  escalation_reason: string | null;
  assignee: string | null;
  created_by: string;
}

export interface SlaBacklogResponse {
  items: SlaBacklogEntry[];
  total: number;
  overdue_pending: number;
}

export async function getSlaBacklog(limit = 50): Promise<SlaBacklogResponse> {
  const response = await fetch(
    `/api/v1/system/operations/sla-backlog?limit=${limit}&overdue_only=true`,
    { cache: "no-store" },
  );
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }
  return (await response.json()) as SlaBacklogResponse;
}

export interface PublishTarget {
  platform: string;
  asset_id: string;
  enabled: boolean;
}

export interface PublishResult {
  platform: string;
  status: string;
  detail: string | null;
  published_url: string | null;
}

export interface PublishResponse {
  campaign_id: string;
  results: PublishResult[];
}

export async function publishCampaign(
  campaignId: string,
  targets: PublishTarget[],
): Promise<PublishResponse> {
  return request<PublishResponse>(`/api/v1/campaigns/${campaignId}/publish`, {
    method: "POST",
    body: JSON.stringify({ targets }),
  });
}

export interface RedisStats {
  redis_version: string | null;
  connected_clients: number | null;
  used_memory_human: string | null;
  uptime_days: number | null;
  total_connections_received: number | null;
  instantaneous_ops_modules: string | null;
  role: string | null;
}

export async function getRedisStats(): Promise<RedisStats> {
  return request<RedisStats>("/api/v1/system/operations/redis-stats");
}

export interface CampaignGroup {
  company_id: string;
  group_id: string;
  name: string;
  campaign_ids: string[];
  created_at: string;
}

export async function createCampaignGroup(name: string, campaignIds: string[]): Promise<CampaignGroup> {
  return request<CampaignGroup>("/api/v1/campaign-groups", {
    method: "POST",
    body: JSON.stringify({ name, campaign_ids: campaignIds }),
  });
}

export async function listCampaignGroups(): Promise<CampaignGroup[]> {
  const res = await request<{ items: CampaignGroup[]; total: number }>("/api/v1/campaign-groups");
  return res.items;
}

export interface WorkOrderListResponse {
  items: WorkOrderRecord[];
  total: number;
  next_cursor: string | null;
}

export async function getCrossCampaignWorkOrders(params?: {
  status?: string;
  assignee?: string;
  limit?: number;
}): Promise<WorkOrderListResponse> {
  const qs = new URLSearchParams();
  if (params?.status) qs.set("status", params.status);
  if (params?.assignee) qs.set("assignee", params.assignee);
  if (params?.limit) qs.set("limit", String(params.limit));
  const query = qs.toString();
  return request<WorkOrderListResponse>(`/api/v1/work-orders/cross-campaign${query ? `?${query}` : ""}`);
}

export async function batchRunCampaigns(campaignIds: string[]): Promise<{ results: { campaign_id: string; status: string }[] }> {
  return request<{ results: { campaign_id: string; status: string }[] }>("/api/v1/campaigns/batch-run", {
    method: "POST",
    body: JSON.stringify({ campaign_ids: campaignIds }),
  });
}

export async function purgeQueueTopic(topic: string, operator?: string): Promise<PurgeTopicResponse> {
  return request<PurgeTopicResponse>("/api/v1/system/operations/purge-topic", {
    method: "POST",
    body: JSON.stringify({ topic, operator }),
  });
}

export async function retryDlqMessage(messageId: string, operator?: string): Promise<RetryDlqResponse> {
  return request<RetryDlqResponse>("/api/v1/system/operations/retry-dlq", {
    method: "POST",
    body: JSON.stringify({ message_id: messageId, operator }),
  });
}

export async function getSystemOperationAuditLogs(params?: {
  page?: number;
  pageSize?: number;
  operator?: string;
  operation?: string;
  result?: string;
  fromTs?: string;
  toTs?: string;
}): Promise<OperationAuditResponse> {
  const query = new URLSearchParams();
  if (params?.page) query.set("page", String(params.page));
  if (params?.pageSize) query.set("page_size", String(params.pageSize));
  if (params?.operator) query.set("operator", params.operator);
  if (params?.operation) query.set("operation", params.operation);
  if (params?.result) query.set("result", params.result);
  if (params?.fromTs) query.set("from_ts", params.fromTs);
  if (params?.toTs) query.set("to_ts", params.toTs);

  const suffix = query.toString();
  return request<OperationAuditResponse>(
    `/api/v1/system/operations/audit-logs${suffix ? `?${suffix}` : ""}`,
  );
}

export function getSystemOperationAuditCsvUrl(params?: {
  operator?: string;
  operation?: string;
  result?: string;
  fromTs?: string;
  toTs?: string;
}): string {
  const apiBase = getApiBase();
  if (!apiBase) {
    throw new Error("NEXT_PUBLIC_CAMPAIGN_API_BASE is not configured");
  }

  const query = new URLSearchParams();
  if (params?.operator) query.set("operator", params.operator);
  if (params?.operation) query.set("operation", params.operation);
  if (params?.result) query.set("result", params.result);
  if (params?.fromTs) query.set("from_ts", params.fromTs);
  if (params?.toTs) query.set("to_ts", params.toTs);

  const suffix = query.toString();
  return `${apiBase}/api/v1/system/operations/audit-logs.csv${suffix ? `?${suffix}` : ""}`;
}

export type ReviewStatus = "review_pending" | "approved" | "rejected";

export type ReviewItem = {
  review_id: string;
  campaign_id: string;
  asset_id: string;
  asset_type?: "copy" | "image" | "video" | "ads" | "unknown" | string;
  asset_name?: string;
  score: number;
  status: ReviewStatus;
  submitted_at: string;
  assignee?: string;
  run_id?: string;
  reject_reason?: string | null;
  rejected_reason?: string | null;
  reason?: string | null;
};

export type ReviewQueueResponse = {
  items: ReviewItem[];
  total: number;
};

export type ReviewActionResult = {
  review_id: string;
  status: ReviewStatus;
  detail: string;
};

export type ReviewAuditEntry = {
  timestamp: string;
  operator: string;
  action: "approve" | "reject";
  target: string;
  result: "ok" | "failed" | "rate_limited";
  reason?: string;
};

export type ReviewAuditResponse = {
  items: ReviewAuditEntry[];
  total: number;
  page: number;
  page_size: number;
};

export type WorkflowTemplateTask = {
  task_type: CampaignTask["task_type"];
  depends_on: string[];
  priority: number;
  acceptance: string[];
};

export type WorkflowTemplate = {
  template_id: string;
  name: string;
  description: string;
  active_version: number;
  status?: "active" | "inactive";
  created_at: string;
};

export type WorkflowTemplateVersion = {
  version: number;
  tasks: WorkflowTemplateTask[];
  created_at: string;
};

export type WorkflowTemplateDetail = {
  template: WorkflowTemplate;
  versions: WorkflowTemplateVersion[];
};

export type WorkflowTemplateListResponse = {
  items: WorkflowTemplate[];
  total: number;
};

export async function listReviewQueue(params?: {
  page?: number;
  pageSize?: number;
  status?: ReviewStatus;
  campaignId?: string;
  runId?: string;
}): Promise<ReviewQueueResponse> {
  const query = new URLSearchParams();
  if (params?.page) query.set("page", String(params.page));
  if (params?.pageSize) query.set("page_size", String(params.pageSize));
  if (params?.status) query.set("status", params.status);
  if (params?.campaignId) query.set("campaign_id", params.campaignId);
  if (params?.runId) query.set("run_id", params.runId);

  const suffix = query.toString();
  return request<ReviewQueueResponse>(`/api/v1/review/items${suffix ? `?${suffix}` : ""}`);
}

export async function approveReviewItem(reviewId: string, operator?: string): Promise<ReviewActionResult> {
  return request<ReviewActionResult>(`/api/v1/review/items/${reviewId}/approve`, {
    method: "POST",
    body: JSON.stringify({ operator }),
  });
}

export async function rejectReviewItem(
  reviewId: string,
  reason: string,
  operator?: string,
): Promise<ReviewActionResult> {
  return request<ReviewActionResult>(`/api/v1/review/items/${reviewId}/reject`, {
    method: "POST",
    body: JSON.stringify({ reason, operator }),
  });
}

export async function submitRevisionRequest(params: {
  reviewId: string;
  campaignId: string;
  taskId: string;
  assetId: string;
  assetType: string;
  rejectReason: string;
  operator?: string;
}): Promise<void> {
  await request("/api/v1/internal/review/revision-request", {
    method: "POST",
    body: JSON.stringify({
      review_id: params.reviewId,
      campaign_id: params.campaignId,
      task_id: params.taskId,
      asset_id: params.assetId,
      asset_type: params.assetType,
      reject_reason: params.rejectReason,
      operator: params.operator,
    }),
  });
}

export async function listReviewAuditLogs(params?: {
  page?: number;
  pageSize?: number;
}): Promise<ReviewAuditResponse> {
  const query = new URLSearchParams();
  if (params?.page) query.set("page", String(params.page));
  if (params?.pageSize) query.set("page_size", String(params.pageSize));

  const suffix = query.toString();
  return request<ReviewAuditResponse>(`/api/v1/review/audit-logs${suffix ? `?${suffix}` : ""}`);
}

export async function listWorkflowTemplates(): Promise<WorkflowTemplate[]> {
  const data = await request<WorkflowTemplateListResponse>("/api/v1/workflow/templates");
  return data.items;
}

export async function getWorkflowTemplate(templateId: string): Promise<WorkflowTemplateDetail> {
  return request<WorkflowTemplateDetail>(`/api/v1/workflow/templates/${templateId}`);
}

export async function createWorkflowTemplate(payload: {
  name: string;
  description: string;
  source_campaign_id?: string;
  tasks?: WorkflowTemplateTask[];
}): Promise<WorkflowTemplateDetail> {
  return request<WorkflowTemplateDetail>("/api/v1/workflow/templates", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function createWorkflowTemplateVersion(
  templateId: string,
  tasks: WorkflowTemplateTask[],
): Promise<WorkflowTemplateDetail> {
  return request<WorkflowTemplateDetail>(`/api/v1/workflow/templates/${templateId}/versions`, {
    method: "POST",
    body: JSON.stringify({ tasks }),
  });
}

export async function deactivateWorkflowTemplate(templateId: string): Promise<{ template_id: string; status: string }> {
  return request<{ template_id: string; status: string }>(`/api/v1/workflow/templates/${templateId}/deactivate`, {
    method: "POST",
  });
}

export async function reactivateWorkflowTemplate(templateId: string): Promise<{ template_id: string; status: string }> {
  return request<{ template_id: string; status: string }>(`/api/v1/workflow/templates/${templateId}/reactivate`, {
    method: "POST",
  });
}

export async function applyWorkflowTemplate(
  templateId: string,
  campaignId: string,
): Promise<{ template_id: string; campaign_id: string; status: string; dispatched_tasks: number }> {
  return request<{ template_id: string; campaign_id: string; status: string; dispatched_tasks: number }>(`/api/v1/workflow/templates/${templateId}/apply`, {
    method: "POST",
    body: JSON.stringify({ campaign_id: campaignId }),
  });
}

export async function listCampaignReferences(campaignId: string): Promise<CampaignReferenceRecord[]> {
  const data = await request<CampaignReferenceListResponse>(`/api/v1/campaigns/${campaignId}/references`);
  return data.items;
}

export async function uploadCampaignReference(
  campaignId: string,
  file: File,
  operator?: string,
): Promise<CampaignReferenceRecord> {
  const formData = new FormData();
  formData.append("file", file);
  if (operator) {
    formData.append("operator", operator);
  }

  return request<CampaignReferenceRecord>(`/api/v1/campaigns/${campaignId}/references/upload`, {
    method: "POST",
    body: formData,
  });
}

export async function attachCampaignReferenceText(params: {
  campaignId: string;
  fileName: string;
  content: string;
  fileType?: string;
  operator?: string;
}): Promise<CampaignReferenceRecord> {
  return request<CampaignReferenceRecord>(`/api/v1/campaigns/${params.campaignId}/references/attach-text`, {
    method: "POST",
    body: JSON.stringify({
      file_name: params.fileName,
      content: params.content,
      file_type: params.fileType ?? "text/plain",
      operator: params.operator ?? "admin",
    }),
  });
}

export async function deleteCampaignReference(campaignId: string, referenceId: string): Promise<{ reference_id: string; deleted: boolean }> {
  return request<{ reference_id: string; deleted: boolean }>(`/api/v1/campaigns/${campaignId}/references/${referenceId}`, {
    method: "DELETE",
  });
}

export async function updateCampaignReference(
  campaignId: string,
  referenceId: string,
  payload: { folder?: string | null; metadata?: Record<string, unknown> },
): Promise<CampaignReferenceRecord> {
  return request<CampaignReferenceRecord>(`/api/v1/campaigns/${campaignId}/references/${referenceId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function listKnowledgeItems(): Promise<KnowledgeItemRecord[]> {
  const data = await request<KnowledgeItemListResponse>("/api/v1/knowledge-items");
  return data.items;
}

export async function uploadKnowledgeItem(
  file: File,
  title?: string,
  description?: string,
  category = "reference-library",
  assetType?: "image" | "video",
): Promise<KnowledgeItemRecord> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("title", title?.trim() || file.name);
  formData.append("description", description?.trim() || "");
  formData.append("category", category);
  if (assetType) formData.append("asset_type", assetType);

  return request<KnowledgeItemRecord>("/api/v1/knowledge-items/upload", {
    method: "POST",
    body: formData,
  });
}

export async function createKnowledgeItem(payload: {
  title: string;
  source?: "ai" | "manual";
  description?: string;
  content_url?: string | null;
  metadata?: Record<string, unknown>;
}): Promise<KnowledgeItemRecord> {
  return request<KnowledgeItemRecord>("/api/v1/knowledge-items", {
    method: "POST",
    body: JSON.stringify({
      title: payload.title,
      source: payload.source ?? "ai",
      description: payload.description ?? "",
      content_url: payload.content_url ?? null,
      metadata: payload.metadata ?? {},
    }),
  });
}

export async function deleteKnowledgeItem(itemId: string): Promise<{ item_id: string; deleted: boolean }> {
  return request<{ item_id: string; deleted: boolean }>(`/api/v1/knowledge-items/${itemId}`, {
    method: "DELETE",
  });
}

export async function updateKnowledgeItem(
  itemId: string,
  payload: { title?: string; description?: string; category?: string; metadata?: Record<string, unknown> },
): Promise<KnowledgeItemRecord> {
  return request<KnowledgeItemRecord>(`/api/v1/knowledge-items/${itemId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function attachKnowledgeItemToCampaign(campaignId: string, item: KnowledgeItemRecord): Promise<CampaignReferenceRecord> {
  const contentUrl = item.content_url;
  if (typeof contentUrl !== "string" || !contentUrl.trim()) {
    // Fall back to attaching description as a text reference if description is available,
    // regardless of whether the item is review_approved.
    if (item.description.trim()) {
      return attachCampaignReferenceText({
        campaignId,
        fileName: `${item.metadata.asset_id ?? item.item_id}.txt`,
        content: item.description,
        fileType: "text/plain",
        operator: "admin",
      });
    }
    throw new Error("Knowledge item has no downloadable content");
  }

  const token = getAccessToken();
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  const apiBase = getApiBase();
  if (!apiBase) {
    throw new Error("NEXT_PUBLIC_CAMPAIGN_API_BASE is not configured");
  }
  const response = await fetch(buildApiUrl(apiBase, contentUrl.trim()), { headers });
  if (!response.ok) {
    throw new Error(`Failed to download knowledge item: ${response.status}`);
  }

  const blob = await response.blob();
  const fileName = typeof item.metadata.file_name === "string" && item.metadata.file_name.trim()
    ? item.metadata.file_name
    : item.title || `${item.item_id}.bin`;
  const fileType = typeof item.metadata.file_type === "string" && item.metadata.file_type.trim()
    ? item.metadata.file_type
    : blob.type || "application/octet-stream";
  const file = new File([blob], fileName, { type: fileType });
  return uploadCampaignReference(campaignId, file, "admin");
}

export async function getCampaignTrace(campaignId: string): Promise<CampaignTraceSummary> {
  const response = await fetch(`/api/campaign-trace/${campaignId}`, { cache: "no-store" });
  if (!response.ok) {
    if (response.status === 404) {
      return { trace: null, event_total: 0, chat_total: 0 };
    }
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }
  return (await response.json()) as CampaignTraceSummary;
}

export async function listCampaignTraceEvents(
  campaignId: string,
  params?: {
    limit?: number;
    cursor?: string;
    eventType?: string;
    actorId?: string;
    keyword?: string;
    fromTs?: string;
    toTs?: string;
  },
): Promise<CampaignTraceEventListResponse> {
  const query = new URLSearchParams();
  if (params?.limit) query.set("limit", String(params.limit));
  if (params?.cursor) query.set("cursor", params.cursor);
  if (params?.eventType) query.set("event_type", params.eventType);
  if (params?.actorId) query.set("actor_id", params.actorId);
  if (params?.keyword) query.set("keyword", params.keyword);
  if (params?.fromTs) query.set("from_ts", params.fromTs);
  if (params?.toTs) query.set("to_ts", params.toTs);
  const suffix = query.toString();
  const response = await fetch(`/api/campaign-trace/${campaignId}/events${suffix ? `?${suffix}` : ""}`, {
    cache: "no-store",
  });
  if (!response.ok) {
    if (response.status === 404) {
      return { items: [], total: 0 };
    }
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }
  return (await response.json()) as CampaignTraceEventListResponse;
}

export async function listCampaignTraceChat(
  campaignId: string,
  params?: { limit?: number; cursor?: string },
): Promise<CampaignTraceChatListResponse> {
  const query = new URLSearchParams();
  if (params?.limit) query.set("limit", String(params.limit));
  if (params?.cursor) query.set("cursor", params.cursor);
  const suffix = query.toString();
  const response = await fetch(`/api/campaign-trace/${campaignId}/chat${suffix ? `?${suffix}` : ""}`, {
    cache: "no-store",
  });
  if (!response.ok) {
    if (response.status === 404) {
      return { items: [], total: 0 };
    }
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }
  return (await response.json()) as CampaignTraceChatListResponse;
}

export async function listCampaignWorkOrders(
  campaignId: string,
  params?: { limit?: number; cursor?: string; status?: WorkOrderStatus; assignee?: string },
): Promise<WorkOrderListResponse> {
  const query = new URLSearchParams();
  if (params?.limit) query.set("limit", String(params.limit));
  if (params?.cursor) query.set("cursor", params.cursor);
  if (params?.status) query.set("status", params.status);
  if (params?.assignee) query.set("assignee", params.assignee);
  const suffix = query.toString();
  const response = await fetch(`/api/campaign-work-orders/campaign/${campaignId}${suffix ? `?${suffix}` : ""}`, {
    cache: "no-store",
  });
  if (!response.ok) {
    if (response.status === 404) {
      return { items: [], total: 0, next_cursor: null };
    }
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }
  return (await response.json()) as WorkOrderListResponse;
}

export async function createCampaignWorkOrder(
  campaignId: string,
  payload: { task_id?: string; title: string; description?: string; assignee?: string; priority?: number; due_at?: string },
  options?: { actorToken?: string },
): Promise<WorkOrderRecord> {
  const response = await fetch(`/api/campaign-work-orders/campaign/${campaignId}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(options?.actorToken ? { "x-chat-actor-token": options.actorToken } : {}),
    },
    body: JSON.stringify(payload),
    cache: "no-store",
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }
  return (await response.json()) as WorkOrderRecord;
}

export async function updateWorkOrder(
  workOrderId: string,
  payload: { title?: string; description?: string; assignee?: string; status?: WorkOrderStatus; priority?: number; due_at?: string },
  options?: { actorToken?: string },
): Promise<WorkOrderRecord> {
  const response = await fetch(`/api/campaign-work-orders/order/${workOrderId}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      ...(options?.actorToken ? { "x-chat-actor-token": options.actorToken } : {}),
    },
    body: JSON.stringify(payload),
    cache: "no-store",
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }
  return (await response.json()) as WorkOrderRecord;
}

export async function listWorkOrderMessages(
  workOrderId: string,
  params?: { limit?: number; cursor?: string },
): Promise<WorkOrderMessageListResponse> {
  const query = new URLSearchParams();
  if (params?.limit) query.set("limit", String(params.limit));
  if (params?.cursor) query.set("cursor", params.cursor);
  const suffix = query.toString();
  const response = await fetch(`/api/campaign-work-orders/order/${workOrderId}/messages${suffix ? `?${suffix}` : ""}`, {
    cache: "no-store",
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }
  return (await response.json()) as WorkOrderMessageListResponse;
}

export async function createWorkOrderMessage(
  workOrderId: string,
  payload: { role?: string; content: string; actor_id?: string },
  options?: { actorToken?: string },
): Promise<WorkOrderMessageRecord> {
  const response = await fetch(`/api/campaign-work-orders/order/${workOrderId}/messages`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(options?.actorToken ? { "x-chat-actor-token": options.actorToken } : {}),
    },
    body: JSON.stringify(payload),
    cache: "no-store",
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }
  return (await response.json()) as WorkOrderMessageRecord;
}
