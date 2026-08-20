"use client";

import { ProtectedRoute } from "@/components/auth/protected-route";
import { useAuth } from "@/lib/auth/context";
import { useI18n } from "@/lib/i18n/context";
import { listRoles, createRole, updateRole, deleteRole, type RoleResponse } from "@/lib/api/auth";
import { useEffect, useState } from "react";

const PERMISSIONS = [
  "campaign:create",
  "campaign:edit",
  "campaign:delete",
  "campaign:read",
  "asset:create",
  "asset:edit",
  "asset:delete",
  "asset:read",
  "review:approve",
  "review:reject",
  "review:revision",
  "publish:execute",
  "member:manage",
  "role:manage",
];

const PERMISSION_LABELS: Record<string, Record<"en" | "zh-Hant" | "ja", string>> = {
  "campaign:create": { en: "Create Campaigns", "zh-Hant": "建立活動", ja: "キャンペーン作成" },
  "campaign:edit": { en: "Edit Campaigns", "zh-Hant": "編輯活動", ja: "キャンペーン編集" },
  "campaign:delete": { en: "Delete Campaigns", "zh-Hant": "刪除活動", ja: "キャンペーン削除" },
  "campaign:read": { en: "View Campaigns", "zh-Hant": "查看活動", ja: "キャンペーン閲覧" },
  "asset:create": { en: "Create Assets", "zh-Hant": "建立素材", ja: "アセット作成" },
  "asset:edit": { en: "Edit Assets", "zh-Hant": "編輯素材", ja: "アセット編集" },
  "asset:delete": { en: "Delete Assets", "zh-Hant": "刪除素材", ja: "アセット削除" },
  "asset:read": { en: "View Assets", "zh-Hant": "查看素材", ja: "アセット閲覧" },
  "review:approve": { en: "Approve Assets", "zh-Hant": "核准素材", ja: "アセット承認" },
  "review:reject": { en: "Reject Assets", "zh-Hant": "退回素材", ja: "アセット却下" },
  "review:revision": { en: "Request Revision", "zh-Hant": "要求修改", ja: "修正依頼" },
  "publish:execute": { en: "Publish", "zh-Hant": "發布", ja: "公開" },
  "member:manage": { en: "Manage Members", "zh-Hant": "管理成員", ja: "メンバー管理" },
  "role:manage": { en: "Manage Roles", "zh-Hant": "管理角色", ja: "ロール管理" },
};

function RolesContent() {
  const { t, locale } = useI18n();
  const { user, isLoading: authLoading } = useAuth();
  const [roles, setRoles] = useState<RoleResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");
  const [newPerms, setNewPerms] = useState<string[]>([]);
  const [editingRole, setEditingRole] = useState<RoleResponse | null>(null);
  const [editName, setEditName] = useState("");
  const [editPerms, setEditPerms] = useState<string[]>([]);
  const [msg, setMsg] = useState<string | null>(null);
  const canManageRoles = user?.permissions.includes("role:manage") ?? false;

  useEffect(() => {
    if (!user?.company_id || !canManageRoles) {
      setLoading(false);
      return;
    }
    listRoles(user.company_id)
      .then(setRoles)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [user?.company_id, canManageRoles]);

  function togglePerm(key: string, mode: "create" | "edit" = "create") {
    const setter = mode === "edit" ? setEditPerms : setNewPerms;
    setter((prev) =>
      prev.includes(key) ? prev.filter((p) => p !== key) : [...prev, key],
    );
  }

  function selectAllPermissions(mode: "create" | "edit" = "create") {
    const setter = mode === "edit" ? setEditPerms : setNewPerms;
    setter((prev) => (prev.length === PERMISSIONS.length ? [] : [...PERMISSIONS]));
  }

  function startEdit(role: RoleResponse) {
    setEditingRole(role);
    setEditName(role.name);
    setEditPerms(role.permissions);
    setMsg(null);
  }

  function cancelEdit() {
    setEditingRole(null);
    setEditName("");
    setEditPerms([]);
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!user?.company_id || !newName.trim()) return;
    try {
      const created = await createRole(user.company_id, newName.trim(), newPerms);
      setRoles((prev) => [...prev, created]);
      setNewName("");
      setNewPerms([]);
      setShowCreate(false);
      setMsg(t("roles.roleCreated"));
    } catch (err) {
      setMsg(localizedRoleError(err, t, "roles.createFailed"));
    }
  }

  async function handleUpdate(e: React.FormEvent) {
    e.preventDefault();
    if (!user?.company_id || !editingRole || !editName.trim()) return;
    try {
      const updated = await updateRole(user.company_id, editingRole.role_id, editName.trim(), editPerms);
      setRoles((prev) => prev.map((role) => role.role_id === updated.role_id ? updated : role));
      cancelEdit();
      setMsg(t("roles.roleUpdated"));
    } catch (err) {
      setMsg(localizedRoleError(err, t, "roles.updateFailed"));
    }
  }

  async function handleDelete(roleId: string) {
    if (!user?.company_id || !window.confirm(t("roles.deleteConfirm"))) return;
    try {
      await deleteRole(user.company_id, roleId);
      setRoles((prev) => prev.filter((r) => r.role_id !== roleId));
      setMsg(t("roles.roleDeleted"));
    } catch (err) {
      setMsg(localizedRoleError(err, t, "roles.cannotDeleteSystem"));
    }
  }

  const systemRoles = roles.filter((r) => r.is_system);
  const customRoles = roles.filter((r) => !r.is_system);

  if (authLoading || loading) {
    return <p className="text-center text-slate-500">{t("system.loading")}</p>;
  }

  if (!canManageRoles) {
    return (
      <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800 dark:border-amber-900/50 dark:bg-amber-950/20 dark:text-amber-200">
        {t("roles.noPermission")}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">{t("roles.title")}</h1>
        <button
          onClick={() => setShowCreate(!showCreate)}
          className="rounded-lg bg-[#0071e3] px-4 py-2 text-sm font-medium text-white hover:bg-[#0071e3]/90"
        >
          {showCreate ? t("common.cancel") : t("roles.create")}
        </button>
      </header>

      {msg && (
        <p className="rounded-lg bg-emerald-50 px-3 py-2 text-xs text-emerald-700">{msg}</p>
      )}

      {showCreate && (
        <div className="rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
          <h2 className="mb-3 text-sm font-semibold">{t("roles.create")}</h2>
          <form onSubmit={handleCreate} className="space-y-3">
            <input
              type="text"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder={t("roles.roleName")}
              required
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
            />
            <button
              type="button"
              onClick={() => selectAllPermissions()}
              className="rounded-lg border border-slate-200 px-3 py-2 text-xs font-medium dark:border-slate-700"
            >
              {newPerms.length === PERMISSIONS.length ? t("roles.clearAll") : t("roles.selectAll")}
            </button>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4">
              {PERMISSIONS.map((p) => (
                <label key={p} className="flex items-center gap-2 text-xs">
                  <input
                    type="checkbox"
                    checked={newPerms.includes(p)}
                    onChange={() => togglePerm(p)}
                    className="rounded border-slate-300"
                  />
                  {permissionLabel(p, locale)}
                </label>
              ))}
            </div>
            <button
              type="submit"
              className="rounded-lg bg-[#0071e3] px-4 py-2 text-sm font-medium text-white hover:bg-[#0071e3]/90"
            >
              {t("roles.create")}
            </button>
          </form>
        </div>
      )}

      {editingRole && (
        <div className="rounded-2xl border border-blue-200 bg-blue-50/50 p-4 dark:border-blue-900/50 dark:bg-blue-950/20">
          <div className="mb-3 flex items-center justify-between gap-3">
            <h2 className="text-sm font-semibold">{t("roles.edit")}</h2>
            <button onClick={cancelEdit} className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium dark:border-slate-700">
              {t("common.cancel")}
            </button>
          </div>
          <form onSubmit={handleUpdate} className="space-y-3">
            <input
              type="text"
              value={editName}
              onChange={(e) => setEditName(e.target.value)}
              placeholder={t("roles.roleName")}
              required
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
            />
            <button
              type="button"
              onClick={() => selectAllPermissions("edit")}
              className="rounded-lg border border-slate-200 px-3 py-2 text-xs font-medium dark:border-slate-700"
            >
              {editPerms.length === PERMISSIONS.length ? t("roles.clearAll") : t("roles.selectAll")}
            </button>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4">
              {PERMISSIONS.map((p) => (
                <label key={p} className="flex items-center gap-2 text-xs">
                  <input
                    type="checkbox"
                    checked={editPerms.includes(p)}
                    onChange={() => togglePerm(p, "edit")}
                    className="rounded border-slate-300"
                  />
                  {permissionLabel(p, locale)}
                </label>
              ))}
            </div>
            <button
              type="submit"
              className="rounded-lg bg-[#0071e3] px-4 py-2 text-sm font-medium text-white hover:bg-[#0071e3]/90"
            >
              {t("common.save")}
            </button>
          </form>
        </div>
      )}

      <>
          {customRoles.length > 0 && (
            <div className="space-y-3">
              <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-400">{t("roles.customRoles")}</h2>
              {customRoles.map((r) => (
                <div key={r.role_id} className="flex items-start justify-between gap-4 rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
                  <div className="min-w-0 flex-1">
                    <p className="font-medium">{r.name}</p>
                    <div className="mt-1 flex flex-wrap gap-1">
                      {r.permissions.map((p) => (
                        <span key={p} className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
                          {permissionLabel(p, locale)}
                        </span>
                      ))}
                    </div>
                  </div>
                  <div className="flex shrink-0 flex-nowrap gap-3 whitespace-nowrap">
                    <button
                      onClick={() => startEdit(r)}
                      className="text-xs text-blue-600 hover:underline"
                    >
                      {t("common.edit")}
                    </button>
                    <button
                      onClick={() => handleDelete(r.role_id)}
                      className="text-xs text-rose-600 hover:underline"
                    >
                      {t("common.delete")}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}

          {customRoles.length === 0 && (
            <p className="text-center text-sm text-slate-400">{t("roles.noCustomRoles")}</p>
          )}

          {systemRoles.length > 0 && (
            <div className="space-y-3">
              <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-400">{t("roles.systemRoles")}</h2>
              {systemRoles.map((r) => (
                <div key={r.role_id} className="flex items-start justify-between gap-4 rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
                  <div className="min-w-0 flex-1">
                    <p className="font-medium">{r.name}</p>
                    <div className="mt-1 flex flex-wrap gap-1">
                      {r.permissions.map((p) => (
                        <span key={p} className="rounded-full bg-blue-50 px-2 py-0.5 text-xs text-blue-600">
                          {permissionLabel(p, locale)}
                        </span>
                      ))}
                    </div>
                  </div>
                  <span className="shrink-0 whitespace-nowrap text-xs text-slate-400">{t("roles.system")}</span>
                </div>
              ))}
            </div>
          )}
      </>
    </div>
  );
}

export default function RolesPage() {
  return (
    <ProtectedRoute>
      <RolesContent />
    </ProtectedRoute>
  );
}

function permissionLabel(permission: string, locale: "en" | "zh-Hant" | "ja") {
  return PERMISSION_LABELS[permission]?.[locale] ?? permission;
}

function localizedRoleError(err: unknown, t: ReturnType<typeof useI18n>["t"], fallbackKey: "roles.createFailed" | "roles.updateFailed" | "roles.cannotDeleteSystem") {
  if (!(err instanceof Error)) return t(fallbackKey);
  if (err.message === "Role with this name already exists") return t("roles.duplicateName");
  if (err.message === "Invalid permissions") return t("roles.invalidPermissions");
  if (err.message === "Insufficient permissions") return t("roles.noPermission");
  return err.message || t(fallbackKey);
}
