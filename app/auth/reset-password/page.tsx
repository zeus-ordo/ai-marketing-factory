"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { resetPassword } from "@/lib/api/auth";
import { useI18n } from "@/lib/i18n/context";

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={null}>
      <ResetPasswordForm />
    </Suspense>
  );
}

function ResetPasswordForm() {
  const { t } = useI18n();
  const searchParams = useSearchParams();
  const token = searchParams.get("token") ?? "";

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [status, setStatus] = useState<"form" | "success" | "error">("form");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const brandTitle = "AI Marketing Factory";
  const successIcon = "🔒";
  const errorIcon = "❌";
  const loadingLabel = "...";

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!token) {
      setStatus("error");
      setError("Missing token");
      return;
    }
    if (password.length < 8) {
      setError(t("auth.weakPassword"));
      return;
    }
    if (password !== confirm) {
      setError(t("auth.passwordMismatch"));
      return;
    }
    setLoading(true);
    try {
      await resetPassword(token, password);
      setStatus("success");
    } catch (err) {
      setStatus("error");
      setError(err instanceof Error ? err.message : t("auth.passwordResetFailed"));
    } finally {
      setLoading(false);
    }
  }

  if (status === "success") {
    return (
      <div className="w-full">
        <div className="mb-8 text-center">
          <h1 className="text-2xl font-semibold tracking-tight text-foreground">
            {brandTitle}
          </h1>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-sm dark:border-slate-800 dark:bg-slate-900">
          <div className="mb-4 text-4xl">{successIcon}</div>
          <h2 className="text-lg font-semibold">{t("auth.passwordResetSuccess")}</h2>
          <Link
            href="/auth/login"
            className="mt-6 inline-block rounded-lg bg-[#0071e3] px-6 py-2.5 text-sm font-medium text-white hover:bg-[#0071e3]/90"
          >
            {t("auth.loginButton")}
          </Link>
        </div>
      </div>
    );
  }

  if (status === "error" && !token) {
    return (
      <div className="w-full">
        <div className="mb-8 text-center">
          <h1 className="text-2xl font-semibold tracking-tight text-foreground">
            {brandTitle}
          </h1>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-sm dark:border-slate-800 dark:bg-slate-900">
          <div className="mb-4 text-4xl">{errorIcon}</div>
          <h2 className="text-lg font-semibold text-rose-600">{t("auth.passwordResetFailed")}</h2>
          <Link
            href="/auth/login"
            className="mt-6 inline-block rounded-lg border border-slate-300 px-6 py-2.5 text-sm font-medium text-slate-700 dark:border-slate-700 dark:text-slate-200"
          >
            {t("auth.loginButton")}
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="w-full">
      <div className="mb-8 text-center">
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">
          {brandTitle}
        </h1>
        <p className="mt-1 text-sm text-slate-500">{t("auth.resetPassword")}</p>
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white p-8 shadow-sm dark:border-slate-800 dark:bg-slate-900">
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
            disabled={loading}
            className="w-full rounded-lg bg-[#0071e3] px-4 py-2.5 text-sm font-medium text-white hover:bg-[#0071e3]/90 disabled:opacity-50"
          >
            {loading ? loadingLabel : t("auth.resetPassword")}
          </button>
        </form>
      </div>
    </div>
  );
}
