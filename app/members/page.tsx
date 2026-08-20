"use client";

import { ProtectedRoute } from "@/components/auth/protected-route";
import { useAuth } from "@/lib/auth/context";
import { useI18n } from "@/lib/i18n/context";
import {
  listMembers,
  inviteMember,
  removeMember,
  listRoles,
  type MemberResponse,
  type RoleResponse,
} from "@/lib/api/auth";
import { useEffect, useState } from "react";

function MembersContent() {
  const { t } = useI18n();
  const { user } = useAuth();
  const [members, setMembers] = useState<MemberResponse[]>([]);
  const [roles, setRoles] = useState<RoleResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRoleId, setInviteRoleId] = useState("");
  const [inviteMode, setInviteMode] = useState<"admin" | "general">("general");
  const [inviteLoading, setInviteLoading] = useState(false);
  const [inviteMsg, setInviteMsg] = useState<string | null>(null);
  const [inviteError, setInviteError] = useState(false);
  const failedMessage = "Failed";
  const removeConfirmMessage = "Remove this member?";
  const noCompanyMessage = "You are not assigned to a company yet.";
  const loadingLabel = "...";

  const canManage = user?.permissions.includes("member:manage");
  const inviteRoles = roles.filter((role) => role.company_id === user?.company_id);
  const adminRole = inviteRoles.find((role) => /admin/i.test(role.name));

  useEffect(() => {
    if (!user?.company_id) return;
    Promise.all([
      listMembers(user.company_id),
      listRoles(user.company_id),
    ])
      .then(([mRes, rRes]) => {
        setMembers(mRes.items);
        setRoles(rRes);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [user?.company_id]);

  async function handleInvite(e: React.FormEvent) {
    e.preventDefault();
    setInviteError(false);
    const resolvedRoleId = inviteMode === "admin" && adminRole?.role_id ? adminRole.role_id : inviteRoleId;
    if (!user?.company_id || !inviteEmail) {
      setInviteMsg("缺少公司或Email資訊");
      setInviteError(true);
      return;
    }
    if (inviteRoles.length === 0) {
      setInviteMsg("目前沒有可指派的公司角色，請先建立公司角色或確認後端 roles 設定");
      setInviteError(true);
      return;
    }
    if (!resolvedRoleId || resolvedRoleId.trim() === "") {
      setInviteMsg("請選擇一個角色");
      setInviteError(true);
      return;
    }
    setInviteLoading(true);
    try {
      await inviteMember(user.company_id, inviteEmail, resolvedRoleId);
      setInviteMsg(`${t("members.inviteSent")} ${inviteEmail}`);
      setInviteError(false);
      setInviteEmail("");
      setInviteRoleId("");
      const res = await listMembers(user.company_id);
      setMembers(res.items);
    } catch (err) {
      setInviteMsg(err instanceof Error ? err.message : failedMessage);
      setInviteError(true);
    } finally {
      setInviteLoading(false);
    }
  }

  async function handleRemove(memberId: string) {
    if (!user?.company_id || !window.confirm(removeConfirmMessage)) return;
    await removeMember(user.company_id, memberId);
    setMembers((prev) => prev.filter((m) => m.member_id !== memberId));
  }

  if (!user?.company_id) {
    return (
      <div className="text-center text-slate-500 py-12">
        {noCompanyMessage}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">{t("members.title")}</h1>
      </header>

      {canManage && (
        <div className="rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
          <h2 className="mb-3 text-sm font-semibold">{t("members.invite")}</h2>
          <form onSubmit={handleInvite} className="flex flex-wrap gap-3">
            <input
              type="email"
              value={inviteEmail}
              onChange={(e) => setInviteEmail(e.target.value)}
              placeholder={t("members.email")}
              required
              className="flex-1 min-w-[200px] rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
            />
            <select
              value={inviteMode}
              onChange={(e) => setInviteMode(e.target.value as "admin" | "general")}
              className="rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
            >
              <option value="admin">{t("members.adminUser")}</option>
              <option value="general">{t("members.generalUser")}</option>
            </select>
            <select
              value={inviteMode === "admin" && adminRole ? adminRole.role_id : inviteRoleId}
              onChange={(e) => setInviteRoleId(e.target.value)}
              required={inviteMode === "general" || !adminRole}
              disabled={inviteMode === "admin" && Boolean(adminRole)}
              className="rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
            >
              <option value="">{inviteMode === "admin" ? t("members.adminAllPermissions") : t("members.generalChoosePermissions")}</option>
              {inviteRoles.map((r) => (
                <option key={r.role_id} value={r.role_id}>
                  {r.name}
                </option>
              ))}
            </select>
            <button
              type="submit"
              disabled={inviteLoading || inviteRoles.length === 0}
              className="rounded-lg bg-[#0071e3] px-4 py-2 text-sm font-medium text-white hover:bg-[#0071e3]/90 disabled:opacity-50"
            >
              {inviteLoading ? loadingLabel : t("members.invite")}
            </button>
          </form>
          {inviteMsg && (
            <p className={`mt-2 text-xs ${inviteError ? "text-rose-600" : "text-emerald-600"}`}>{inviteMsg}</p>
          )}
          {inviteRoles.length === 0 ? (
            <p className="mt-2 text-xs text-amber-600">沒有可指派的公司角色。平台角色不可直接指派給成員。</p>
          ) : null}
        </div>
      )}

      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
        <table className="min-w-full text-left text-sm">
          <thead className="border-b border-slate-200 bg-slate-50 text-slate-500 dark:border-slate-800 dark:bg-slate-950">
            <tr>
              <th className="px-4 py-3">{t("members.email")}</th>
              <th className="px-4 py-3">{t("members.roles")}</th>
              <th className="px-4 py-3">{t("members.status")}</th>
              {canManage && <th className="px-4 py-3">{t("members.actions")}</th>}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td className="px-4 py-8 text-center text-slate-500" colSpan={4}>
                  {t("system.loading")}
                </td>
              </tr>
            ) : members.length === 0 ? (
              <tr>
                <td className="px-4 py-8 text-center text-slate-500" colSpan={4}>
                  {t("members.noMembers")}
                </td>
              </tr>
            ) : (
              members.map((m) => (
                <tr key={m.member_id} className="border-b border-slate-200/70 last:border-none dark:border-slate-800">
                  <td className="px-4 py-3">
                    <div className="font-medium">{m.email}</div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-1">
                      {m.roles.map((r) => (
                        <span
                          key={r.role_id}
                          className={`rounded-full px-2 py-0.5 text-xs ${
                            r.is_system
                              ? "bg-blue-100 text-blue-700"
                              : "bg-slate-100 text-slate-600"
                          }`}
                        >
                          {r.name}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs ${
                        m.email_verified
                          ? "bg-emerald-100 text-emerald-700"
                          : "bg-amber-100 text-amber-700"
                      }`}
                    >
                      {m.email_verified ? t("members.verified") : t("members.pending")}
                    </span>
                  </td>
                  {canManage && (
                    <td className="px-4 py-3">
                      {m.member_id !== user?.member_id && (
                        <button
                          onClick={() => handleRemove(m.member_id)}
                          className="text-xs text-rose-600 hover:underline"
                        >
                          {t("members.remove")}
                        </button>
                      )}
                    </td>
                  )}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function MembersPage() {
  return (
    <ProtectedRoute>
      <MembersContent />
    </ProtectedRoute>
  );
}
