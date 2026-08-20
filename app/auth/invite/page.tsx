"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { getInvitation, acceptInvitation } from "@/lib/api/auth";
import { useI18n } from "@/lib/i18n/context";
import type { InvitationInfo } from "@/lib/api/auth";

export default function InvitePage() {
  return (
    <Suspense fallback={null}>
      <InviteForm />
    </Suspense>
  );
}

function InviteForm() {
  const { t } = useI18n();
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token") ?? "";

  const [invitation, setInvitation] = useState<InvitationInfo | null>(null);
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(Boolean(token));
  const [submitting, setSubmitting] = useState(false);
  const brandTitle = "AI Marketing Factory";
  const loadingIcon = "⏳";
  const errorIcon = "❌";
  const inviteIcon = "🤝";
  const loadingInvitation = "Loading invitation...";
  const invalidInvitation = "Invalid or expired invitation";
  const registerInstead = "Register instead";
  const roleLabel = "Role";

  useEffect(() => {
    if (!token) {
      return;
    }
    getInvitation(token)
      .then(setInvitation)
      .catch(() => setInvitation(null))
      .finally(() => setLoading(false));
  }, [token]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (password.length < 8) {
      setError(t("auth.weakPassword"));
      return;
    }
    if (password !== confirm) {
      setError(t("auth.passwordMismatch"));
      return;
    }
    setSubmitting(true);
    try {
      const result = await acceptInvitation(token, password);
      localStorage.setItem("access_token", result.access_token);
      localStorage.setItem("refresh_token", result.refresh_token);
      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to accept invitation");
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) {
    return (
      <div className="w-full">
        <div className="mb-8 text-center">
          <h1 className="text-2xl font-semibold tracking-tight text-foreground">{brandTitle}</h1>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-sm dark:border-slate-800 dark:bg-slate-900">
          <div className="text-4xl animate-pulse">{loadingIcon}</div>
          <p className="mt-2 text-sm text-slate-500">{loadingInvitation}</p>
        </div>
      </div>
    );
  }

  if (!invitation) {
    return (
      <div className="w-full">
        <div className="mb-8 text-center">
          <h1 className="text-2xl font-semibold tracking-tight text-foreground">{brandTitle}</h1>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-sm dark:border-slate-800 dark:bg-slate-900">
          <div className="text-4xl">{errorIcon}</div>
          <h2 className="mt-4 text-lg font-semibold">{invalidInvitation}</h2>
          <Link href="/auth/register" className="mt-6 inline-block rounded-lg border border-slate-300 px-6 py-2.5 text-sm font-medium text-slate-700 dark:border-slate-700 dark:text-slate-200">
            {registerInstead}
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="w-full">
      <div className="mb-8 text-center">
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">{brandTitle}</h1>
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white p-8 shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <div className="mb-6 text-center">
          <div className="text-4xl mb-2">{inviteIcon}</div>
          <h2 className="text-lg font-semibold">{t("auth.invitationTitle")}</h2>
          <p className="mt-1 text-sm text-slate-500">
            {t("auth.invitationToJoin")} <strong>{invitation.company_name}</strong>
          </p>
          <p className="mt-1 text-xs text-slate-400">
            {roleLabel}: <span className="font-medium">{invitation.role_name}</span>
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="password" className="block text-xs font-medium text-slate-600 dark:text-slate-300">
              {t("auth.password")}
            </label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm shadow-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary dark:border-slate-700 dark:bg-slate-950"
            />
          </div>

          <div>
            <label htmlFor="confirm" className="block text-xs font-medium text-slate-600 dark:text-slate-300">
              {t("auth.confirmPassword")}
            </label>
            <input
              id="confirm"
              type="password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              required
              className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm shadow-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary dark:border-slate-700 dark:bg-slate-950"
            />
          </div>

          {error && (
            <p className="rounded-lg bg-rose-50 px-3 py-2 text-xs text-rose-600">{error}</p>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="w-full rounded-lg bg-[#0071e3] px-4 py-2.5 text-sm font-medium text-white hover:bg-[#0071e3]/90 disabled:opacity-50"
          >
            {submitting ? t("common.loading") : t("auth.acceptInvitation")}
          </button>
        </form>
      </div>
    </div>
  );
}
