"use client";

import Link from "next/link";
import { useState } from "react";
import { register } from "@/lib/api/auth";
import { useI18n } from "@/lib/i18n/context";

export default function RegisterPage() {
  const { t } = useI18n();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [loading, setLoading] = useState(false);
  const brandTitle = "AI Marketing Factory";
  const emailIcon = "✉️";

  function passwordStrength(p: string): string {
    if (p.length === 0) return "";
    if (p.length < 8) return "bg-rose-400";
    if (p.length < 12) return "bg-amber-400";
    return "bg-emerald-400";
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
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
      await register(email, password);
      setSuccess(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed");
    } finally {
      setLoading(false);
    }
  }

  if (success) {
    return (
      <div className="w-full">
        <div className="mb-8 text-center">
          <h1 className="text-2xl font-semibold tracking-tight text-foreground">
            {brandTitle}
          </h1>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-sm dark:border-slate-800 dark:bg-slate-900">
          <div className="mb-4 text-4xl">{emailIcon}</div>
          <h2 className="text-lg font-semibold">{t("auth.emailSent")}</h2>
          <p className="mt-2 text-sm text-slate-500">{email}</p>
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

  return (
    <div className="w-full">
      <div className="mb-8 text-center">
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">
          {brandTitle}
        </h1>
        <p className="mt-1 text-sm text-slate-500">{t("auth.register")}</p>
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white p-8 shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label
              htmlFor="email"
              className="block text-xs font-medium text-slate-600 dark:text-slate-300"
            >
              {t("auth.email")}
            </label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="email"
              className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm shadow-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary dark:border-slate-700 dark:bg-slate-950"
            />
          </div>

          <div>
            <label
              htmlFor="password"
              className="block text-xs font-medium text-slate-600 dark:text-slate-300"
            >
              {t("auth.password")}
            </label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="new-password"
              className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm shadow-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary dark:border-slate-700 dark:bg-slate-950"
            />
            {password.length > 0 && (
              <div className="mt-1.5 h-1 rounded-full bg-slate-100">
                <div
                  className={`h-1 rounded-full transition-all ${passwordStrength(password)}`}
                  style={{ width: `${Math.min(100, (password.length / 16) * 100)}%` }}
                />
              </div>
            )}
          </div>

          <div>
            <label
              htmlFor="confirm"
              className="block text-xs font-medium text-slate-600 dark:text-slate-300"
            >
              {t("auth.confirmPassword")}
            </label>
            <input
              id="confirm"
              type="password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              required
              autoComplete="new-password"
              className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm shadow-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary dark:border-slate-700 dark:bg-slate-950"
            />
          </div>

          {error && (
            <p className="rounded-lg bg-rose-50 px-3 py-2 text-xs text-rose-600">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-lg bg-[#0071e3] px-4 py-2.5 text-sm font-medium text-white hover:bg-[#0071e3]/90 disabled:opacity-50"
          >
            {loading ? "..." : t("auth.registerButton")}
          </button>
        </form>

        <div className="mt-4 text-center text-xs">
          <Link
            href="/auth/login"
            className="text-slate-500 hover:text-slate-700 dark:hover:text-slate-300"
          >
            {t("auth.hasAccount")}{" "}
            <span className="text-primary">{t("auth.login")}</span>
          </Link>
        </div>
      </div>
    </div>
  );
}
