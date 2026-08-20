"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { verifyEmail } from "@/lib/api/auth";
import { useI18n } from "@/lib/i18n/context";

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={null}>
      <VerifyEmailForm />
    </Suspense>
  );
}

function VerifyEmailForm() {
  const { t } = useI18n();
  const searchParams = useSearchParams();
  const token = searchParams.get("token") ?? "";

  const [status, setStatus] = useState<"loading" | "success" | "error">(token ? "loading" : "error");
  const [message, setMessage] = useState(token ? "" : t("auth.verificationFailed"));
  const brandTitle = "AI Marketing Factory";
  const loadingIcon = "⏳";
  const successIcon = "✅";
  const errorIcon = "❌";
  const verifying = "Verifying...";

  useEffect(() => {
    if (!token) {
      return;
    }

    verifyEmail(token)
      .then(() => {
        setStatus("success");
        setMessage(t("auth.emailVerified"));
      })
      .catch((err) => {
        setStatus("error");
        setMessage(err instanceof Error ? err.message : t("auth.verificationFailed"));
      });
  }, [token, t]);

  return (
    <div className="w-full">
      <div className="mb-8 text-center">
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">
          {brandTitle}
        </h1>
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-sm dark:border-slate-800 dark:bg-slate-900">
        {status === "loading" && (
          <>
            <div className="mb-4 text-4xl animate-pulse">{loadingIcon}</div>
            <p className="text-sm text-slate-500">{verifying}</p>
          </>
        )}

        {status === "success" && (
          <>
            <div className="mb-4 text-4xl">{successIcon}</div>
            <h2 className="text-lg font-semibold">{message}</h2>
            <Link
              href="/auth/login"
              className="mt-6 inline-block rounded-lg bg-[#0071e3] px-6 py-2.5 text-sm font-medium text-white hover:bg-[#0071e3]/90"
            >
              {t("auth.loginButton")}
            </Link>
          </>
        )}

        {status === "error" && (
          <>
            <div className="mb-4 text-4xl">{errorIcon}</div>
            <h2 className="text-lg font-semibold text-rose-600">{message}</h2>
            <Link
              href="/auth/register"
              className="mt-6 inline-block rounded-lg border border-slate-300 px-6 py-2.5 text-sm font-medium text-slate-700 dark:border-slate-700 dark:text-slate-200"
            >
              {t("auth.registerButton")}
            </Link>
          </>
        )}
      </div>
    </div>
  );
}
