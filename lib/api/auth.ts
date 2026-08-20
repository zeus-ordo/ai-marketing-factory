const API_BASE =
  typeof window !== "undefined"
    ? (process.env.NEXT_PUBLIC_MEMBERSHIP_API_BASE ?? "http://localhost:8095")
    : "http://localhost:8095";

function buildUrl(path: string): string {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  if (!API_BASE || API_BASE === "/") return normalizedPath;
  return `${API_BASE.replace(/\/$/, "")}${normalizedPath}`;
}

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  token_type?: string;
}

export interface MemberProfile {
  member_id: string;
  email: string;
  company_id: string | null;
  permissions: string[];
}

export interface RoleResponse {
  role_id: string;
  company_id: string | null;
  name: string;
  is_system: boolean;
  permissions: string[];
  created_at: string;
}

export interface MemberResponse {
  member_id: string;
  email: string;
  company_id: string | null;
  email_verified: boolean;
  is_active: boolean;
  roles: RoleResponse[];
  created_at: string;
}

export interface InvitationInfo {
  invitation_id: string;
  company_name: string;
  role_name: string;
  email: string;
  status: string;
  expires_at: string;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {};
  if (init?.headers) {
    const h = init.headers as Record<string, string>;
    for (const [k, v] of Object.entries(h)) {
      headers[k] = v;
    }
  }
  if (!(init?.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }
  const token =
    typeof window !== "undefined" ? localStorage.getItem("access_token") : null;
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(buildUrl(path), {
    ...init,
    headers,
  });

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
      if (errorText.trim()) message = errorText;
    }
    throw new Error(message);
  }

  if (response.status === 204) {
    return {} as T;
  }

  return response.json() as Promise<T>;
}

// ─── Auth ────────────────────────────────────────────────────────────────────

export async function login(email: string, password: string): Promise<LoginResponse> {
  return request<LoginResponse>("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export async function register(email: string, password: string): Promise<void> {
  await request("/api/v1/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export async function verifyEmail(token: string): Promise<void> {
  await request("/api/v1/auth/verify-email", {
    method: "POST",
    body: JSON.stringify({ token }),
  });
}

export async function refresh(refreshToken: string): Promise<LoginResponse> {
  return request<LoginResponse>("/api/v1/auth/refresh", {
    method: "POST",
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
}

export async function logout(refreshToken: string): Promise<void> {
  await request("/api/v1/auth/logout", {
    method: "POST",
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
}

export function logoutKeepalive(refreshToken: string): void {
  if (typeof window === "undefined" || !refreshToken) return;
  const body = JSON.stringify({ refresh_token: refreshToken });
  if (navigator.sendBeacon) {
    const blob = new Blob([body], { type: "application/json" });
    if (navigator.sendBeacon(buildUrl("/api/v1/auth/logout-beacon"), blob)) return;
  }
  void fetch(buildUrl("/api/v1/auth/logout"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
    keepalive: true,
  }).catch(() => {
    // Browser shutdown may cancel keepalive requests; local tokens are still cleared by caller.
  });
}

export async function forgotPassword(email: string): Promise<void> {
  await request("/api/v1/auth/forgot-password", {
    method: "POST",
    body: JSON.stringify({ email }),
  });
}

export async function resetPassword(token: string, newPassword: string): Promise<void> {
  await request("/api/v1/auth/reset-password", {
    method: "POST",
    body: JSON.stringify({ token, new_password: newPassword }),
  });
}

export async function getMe(): Promise<MemberProfile> {
  return request<MemberProfile>("/api/v1/auth/me");
}

// ─── Invitation ───────────────────────────────────────────────────────────────

export async function getInvitation(token: string): Promise<InvitationInfo> {
  return request<InvitationInfo>(`/api/v1/invitation/accept?token=${encodeURIComponent(token)}`);
}

export async function acceptInvitation(
  token: string,
  password: string,
): Promise<LoginResponse> {
  return request<LoginResponse>(`/api/v1/invitation/accept?token=${encodeURIComponent(token)}`, {
    method: "POST",
    body: JSON.stringify({ password }),
  });
}

// ─── Company Members ──────────────────────────────────────────────────────────

export async function listMembers(companyId: string): Promise<{ items: MemberResponse[]; total: number }> {
  return request<{ items: MemberResponse[]; total: number }>(
    `/api/v1/companies/${companyId}/members`,
  );
}

export async function inviteMember(
  companyId: string,
  email: string,
  roleId: string,
): Promise<void> {
  await request(`/api/v1/companies/${companyId}/members/invite`, {
    method: "POST",
    body: JSON.stringify({ email, role_id: roleId }),
  });
}

export async function removeMember(companyId: string, memberId: string): Promise<void> {
  await request(`/api/v1/companies/${companyId}/members/${memberId}`, {
    method: "DELETE",
  });
}

export async function updateMemberRoles(
  companyId: string,
  memberId: string,
  roleIds: string[],
): Promise<void> {
  await request(`/api/v1/companies/${companyId}/members/${memberId}/roles`, {
    method: "PUT",
    body: JSON.stringify({ role_ids: roleIds }),
  });
}

// ─── Roles ────────────────────────────────────────────────────────────────────

export async function listRoles(companyId: string): Promise<RoleResponse[]> {
  return request<RoleResponse[]>(`/api/v1/companies/${companyId}/roles`);
}

export async function createRole(
  companyId: string,
  name: string,
  permissions: string[],
): Promise<RoleResponse> {
  return request<RoleResponse>(`/api/v1/companies/${companyId}/roles`, {
    method: "POST",
    body: JSON.stringify({ name, permissions }),
  });
}

export async function updateRole(
  companyId: string,
  roleId: string,
  name: string,
  permissions: string[],
): Promise<RoleResponse> {
  return request<RoleResponse>(`/api/v1/companies/${companyId}/roles/${roleId}`, {
    method: "PUT",
    body: JSON.stringify({ name, permissions }),
  });
}

export async function deleteRole(companyId: string, roleId: string): Promise<void> {
  await request(`/api/v1/companies/${companyId}/roles/${roleId}`, {
    method: "DELETE",
  });
}

// ─── Platform (Developer) ──────────────────────────────────────────────────────

function getPlatformKey(): string {
  if (typeof window !== "undefined") {
    return localStorage.getItem("platform_key") ?? "";
  }
  return "";
}

async function platformRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {};
  if (init?.headers) {
    const h = init.headers as Record<string, string>;
    for (const [k, v] of Object.entries(h)) {
      headers[k] = v;
    }
  }
  if (!(init?.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }
  const platformKey = getPlatformKey();
  if (platformKey) {
    headers["X-Platform-Key"] = platformKey;
  }
  const response = await fetch(buildUrl(path), {
    ...init,
    headers,
  });
  if (!response.ok) {
    const contentType = response.headers.get("content-type") ?? "";
    let message = `Request failed: ${response.status}`;
    if (contentType.includes("application/json")) {
      const payload = (await response.json()) as { detail?: unknown };
      if (typeof payload.detail === "string" && payload.detail.trim()) {
        message = payload.detail;
      }
    }
    throw new Error(message);
  }
  if (response.status === 204) return {} as T;
  return response.json() as Promise<T>;
}

export interface CompanyResponse {
  company_id: string;
  name: string;
  slug: string;
  created_at: string;
  updated_at: string;
}

export async function platformListCompanies(): Promise<{ items: CompanyResponse[]; total: number }> {
  return platformRequest<{ items: CompanyResponse[]; total: number }>("/api/v1/platform/companies");
}

export async function platformCreateCompany(name: string, slug: string): Promise<CompanyResponse> {
  return platformRequest<CompanyResponse>("/api/v1/platform/companies", {
    method: "POST",
    body: JSON.stringify({ name, slug }),
  });
}

export async function platformCreateAdmin(
  companyId: string,
  email: string,
  password: string,
): Promise<void> {
  await platformRequest(`/api/v1/platform/companies/${companyId}/admin`, {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export async function platformListMembers(
  companyId: string,
): Promise<{ items: MemberResponse[]; total: number }> {
  return platformRequest<{ items: MemberResponse[]; total: number }>(
    `/api/v1/platform/companies/${companyId}/members`,
  );
}

export function setPlatformKey(key: string): void {
  if (typeof window !== "undefined") {
    localStorage.setItem("platform_key", key);
  }
}

export interface AuditLogEntry {
  log_id: string;
  member_id: string | null;
  company_id: string | null;
  action: string;
  resource_type: string | null;
  resource_id: string | null;
  ip_address: string | null;
  metadata: Record<string, unknown> | null;
  created_at: string;
}

export interface AuditLogListResponse {
  items: AuditLogEntry[];
  total: number;
  page: number;
  page_size: number;
}

export async function platformListAuditLogs(params?: {
  page?: number;
  page_size?: number;
  action?: string;
  member_id?: string;
  company_id?: string;
}): Promise<AuditLogListResponse> {
  const qs = new URLSearchParams();
  if (params?.page) qs.set("page", String(params.page));
  if (params?.page_size) qs.set("page_size", String(params.page_size));
  if (params?.action) qs.set("action", params.action);
  if (params?.member_id) qs.set("member_id", params.member_id);
  if (params?.company_id) qs.set("company_id", params.company_id);
  const query = qs.toString();
  return platformRequest<AuditLogListResponse>(
    `/api/v1/platform/audit-logs${query ? `?${query}` : ""}`,
  );
}

// ─── LLM Usage ──────────────────────────────────────────────────────────────────

export interface LlmUsageRecord {
  usage_id: string;
  company_id: string;
  model: string;
  provider: string;
  prompt_tokens: number;
  completion_tokens: number;
  request_count: number;
  cost_usd: number;
  created_at: string;
}

export interface LlmUsageListResponse {
  items: LlmUsageRecord[];
  total: number;
  page: number;
  page_size: number;
}

export interface LlmUsageSummaryByModel {
  model: string;
  provider: string;
  prompt_tokens: number;
  completion_tokens: number;
  request_count: number;
  cost_usd: number;
}

export interface LlmUsageSummaryResponse {
  total_prompt_tokens: number;
  total_completion_tokens: number;
  total_request_count: number;
  total_cost_usd: number;
  by_model: LlmUsageSummaryByModel[];
}

export interface LlmModelPricingRecord {
  pricing_id: string;
  model: string;
  provider: string;
  prompt_price_per_m: number;
  completion_price_per_m: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface LlmPricingListResponse {
  items: LlmModelPricingRecord[];
  total: number;
}

export async function platformListLlmUsage(params?: {
  page?: number;
  page_size?: number;
  company_id?: string;
  model?: string;
  from?: string;
  to?: string;
}): Promise<LlmUsageListResponse> {
  const qs = new URLSearchParams();
  if (params?.page) qs.set("page", String(params.page));
  if (params?.page_size) qs.set("page_size", String(params.page_size));
  if (params?.company_id) qs.set("company_id", params.company_id);
  if (params?.model) qs.set("model", params.model);
  if (params?.from) qs.set("from_ts", params.from);
  if (params?.to) qs.set("to_ts", params.to);
  const query = qs.toString();
  return platformRequest<LlmUsageListResponse>(
    `/api/v1/platform/usage${query ? `?${query}` : ""}`,
  );
}

export async function platformSummarizeLlmUsage(params?: {
  company_id?: string;
  from?: string;
  to?: string;
}): Promise<LlmUsageSummaryResponse> {
  const qs = new URLSearchParams();
  if (params?.company_id) qs.set("company_id", params.company_id);
  if (params?.from) qs.set("from_ts", params.from);
  if (params?.to) qs.set("to_ts", params.to);
  const query = qs.toString();
  return platformRequest<LlmUsageSummaryResponse>(
    `/api/v1/platform/usage/summary${query ? `?${query}` : ""}`,
  );
}

export async function platformListPricing(): Promise<LlmPricingListResponse> {
  return platformRequest<LlmPricingListResponse>(`/api/v1/platform/usage/pricing`);
}

export async function platformUpsertPricing(payload: {
  model: string;
  provider: string;
  prompt_price_per_m: number;
  completion_price_per_m: number;
}): Promise<LlmModelPricingRecord> {
  return platformRequest<LlmModelPricingRecord>(`/api/v1/platform/usage/pricing`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function platformDeletePricing(model: string): Promise<void> {
  await platformRequest(`/api/v1/platform/usage/pricing/${encodeURIComponent(model)}`, {
    method: "DELETE",
  });
}
