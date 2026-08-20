"use client";

import Link from "next/link";
import { useState } from "react";
import { forgotPassword } from "@/lib/api/auth";
import { useI18n } from "@/lib/i18n/context";

export default function ForgotPasswordPage() {
  const { t } = useI18n();
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [loading, setLoading] = useState(false);
  const brandTitle = "AI Marketing Factory";
  const emailIcon = "✉️";
  const sentTitle = "Check your email";
  const sentDescription = "If an account with that email exists, we sent a password reset link.";
  const backToLogin = "Back to login";
  const resetTitle = "Reset password";
  const resetDescription = "Enter your email and we will send you a reset link.";
  const loadingLabel = "...";
  const sendResetLink = "Send reset link";

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    try {
      await forgotPassword(email);
      setSent(true);
    } catch {
      // Don't reveal if email exists
      setSent(true);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="w-full">
      <div className="mb-8 text-center">
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">{brandTitle}</h1>
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white p-8 shadow-sm dark:border-slate-800 dark:bg-slate-900">
        {sent ? (
          <div className="text-center">
            <div className="text-4xl mb-3">{emailIcon}</div>
            <h2 className="text-lg font-semibold">{sentTitle}</h2>
            <p className="mt-2 text-sm text-slate-500">
              {sentDescription}
            </p>
            <Link
              href="/auth/login"
              className="mt-6 inline-block rounded-lg bg-[#0071e3] px-6 py-2.5 text-sm font-medium text-white hover:bg-[#0071e3]/90"
            >
              {backToLogin}
            </Link>
          </div>
        ) : (
          <>
            <h2 className="text-lg font-semibold mb-1">{resetTitle}</h2>
            <p className="text-sm text-slate-500 mb-4">{resetDescription}</p>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label htmlFor="email" className="block text-xs font-medium text-slate-600 dark:text-slate-300">
                  {t("auth.email")}
                </label>
                <input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm shadow-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary dark:border-slate-700 dark:bg-slate-950"
                />
              </div>
              <button
                type="submit"
                disabled={loading}
                className="w-full rounded-lg bg-[#0071e3] px-4 py-2.5 text-sm font-medium text-white hover:bg-[#0071e3]/90 disabled:opacity-50"
              >
                {loading ? loadingLabel : sendResetLink}
              </button>
            </form>
            <div className="mt-4 text-center text-xs">
              <Link href="/auth/login" className="text-primary hover:underline">{backToLogin}</Link>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
