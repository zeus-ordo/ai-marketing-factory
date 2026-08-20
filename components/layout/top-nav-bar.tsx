"use client";

import { Bell, CircleHelp, Search, LogOut, User, ChevronDown } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useAuth } from "@/lib/auth/context";
import { useI18n } from "@/lib/i18n/context";

export function TopNavBar() {
  const { locale, locales, setLocale, t } = useI18n();
  const { user, isLoading, logout } = useAuth();
  const router = useRouter();
  const [menuOpen, setMenuOpen] = useState(false);

  async function handleLogout() {
    await logout();
    setMenuOpen(false);
    router.push("/auth/login");
  }

  return (
    <header className="sticky top-0 z-30 border-b border-slate-200/70 bg-white/70 px-6 py-3 backdrop-blur-md md:px-8 dark:border-slate-800 dark:bg-slate-950/75">
      <div className="flex items-center gap-3">
        <div className="relative w-full max-w-xl">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            placeholder={t("app.searchPlaceholder")}
            className="w-full rounded-xl border border-slate-200 bg-white/80 py-2 pl-9 pr-3 text-sm outline-none transition focus:border-blue-500 dark:border-slate-700 dark:bg-slate-900"
          />
        </div>

        <div className="hidden shrink-0 items-center gap-2 lg:flex">
          <Link
            href="/campaigns#create-campaign"
            className="rounded-xl bg-blue-600 px-3 py-2 text-xs font-semibold text-white shadow-sm transition hover:bg-blue-700"
          >
            {t("campaigns.form.title")}
          </Link>
          <Link
            href="/campaigns"
            className="rounded-xl border border-slate-200 px-3 py-2 text-xs font-medium text-slate-700 transition hover:bg-blue-50 hover:text-blue-700 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800 dark:hover:text-blue-300"
          >
            {t("nav.campaigns")}
          </Link>
        </div>

        <label className="sr-only" htmlFor="locale-switcher">{t("app.language")}</label>
        <select
          id="locale-switcher"
          value={locale}
          onChange={(event) => setLocale(event.target.value as typeof locale)}
          className="rounded-xl border border-slate-200 bg-white px-2 py-2 text-xs text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
        >
          {locales.map((item) => (
            <option key={item} value={item}>{item}</option>
          ))}
        </select>

        <button className="rounded-xl border border-slate-200 p-2 text-slate-600 transition hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800">
          <Bell className="h-4 w-4" aria-hidden />
        </button>
        <button className="rounded-xl border border-slate-200 p-2 text-slate-600 transition hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800">
          <CircleHelp className="h-4 w-4" aria-hidden />
        </button>

        {/* Auth section */}
        {isLoading ? (
          <div className="h-9 w-9 rounded-full bg-slate-200 animate-pulse" />
        ) : user ? (
          <div className="relative">
            <button
              onClick={() => setMenuOpen(!menuOpen)}
              className="flex items-center gap-2 rounded-xl border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-700 transition hover:bg-slate-100 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
            >
              <User className="h-4 w-4" />
              <span className="max-w-[120px] truncate">{user.email}</span>
              <ChevronDown className="h-3 w-3" />
            </button>

            {menuOpen && (
              <div className="absolute right-0 top-full mt-1 w-48 rounded-xl border border-slate-200 bg-white py-1 shadow-lg dark:border-slate-700 dark:bg-slate-900">
                {user.company_id && (
                  <Link
                    href="/members"
                    onClick={() => setMenuOpen(false)}
                    className="flex w-full items-center gap-2 px-4 py-2 text-xs text-slate-700 hover:bg-slate-50 dark:text-slate-200 dark:hover:bg-slate-800"
                  >
                    <User className="h-3.5 w-3.5" />
                    {t("auth.myCompany")}
                  </Link>
                )}
                {user.permissions.includes("role:manage") && (
                  <Link
                    href="/roles"
                    onClick={() => setMenuOpen(false)}
                    className="flex w-full items-center gap-2 px-4 py-2 text-xs text-slate-700 hover:bg-slate-50 dark:text-slate-200 dark:hover:bg-slate-800"
                  >
                    <User className="h-3.5 w-3.5" />
                    {t("roles.title")}
                  </Link>
                )}
                <button
                  onClick={handleLogout}
                  className="flex w-full items-center gap-2 px-4 py-2 text-xs text-rose-600 hover:bg-slate-50 dark:text-rose-400 dark:hover:bg-slate-800"
                >
                  <LogOut className="h-3.5 w-3.5" />
                  {t("auth.logout")}
                </button>
              </div>
            )}
          </div>
        ) : (
          <div className="flex items-center gap-2">
            <Link
              href="/auth/login"
              className="rounded-xl border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-700 transition hover:bg-slate-100 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
            >
              {t("auth.login")}
            </Link>
            <Link
              href="/auth/register"
              className="rounded-xl bg-[#0071e3] px-3 py-1.5 text-xs font-medium text-white transition hover:bg-[#0071e3]/90"
            >
              {t("auth.register")}
            </Link>
          </div>
        )}
      </div>
    </header>
  );
}
