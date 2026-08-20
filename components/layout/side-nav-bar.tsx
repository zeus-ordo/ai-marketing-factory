"use client";

import Link from "next/link";
import { navItems } from "@/lib/navigation";
import { useAuth } from "@/lib/auth/context";
import { useI18n } from "@/lib/i18n/context";

function canSeeNavItem(href: string, permissions: string[]) {
  if (href === "/review") {
    return permissions.some((permission) => ["review:approve", "review:reject", "review:revision"].includes(permission));
  }
  if (href === "/roles") {
    return permissions.includes("role:manage");
  }
  return true;
}

export function SideNavBar() {
  const { t } = useI18n();
  const { user } = useAuth();
  const visibleItems = navItems.filter((item) => canSeeNavItem(item.href, user?.permissions ?? []));

  return (
    <aside className="sticky top-0 hidden h-screen w-64 shrink-0 overflow-y-auto border-r border-slate-200/80 bg-white/90 px-4 py-6 backdrop-blur xl:block dark:border-slate-800 dark:bg-slate-950/85">
      <p className="mb-8 px-2 text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">
        {t("app.title")}
      </p>

      <nav className="space-y-1">
        {visibleItems.map((item) => {
          const Icon = item.icon;

          return (
            <Link
              key={item.href}
              href={item.href}
              className="group flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium text-slate-600 transition hover:bg-blue-50 hover:text-blue-700 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-blue-300"
            >
              <Icon className="h-4 w-4" aria-hidden />
              {t(item.key)}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}

export function MobileNavBar() {
  const { t } = useI18n();
  const { user } = useAuth();
  const visibleItems = navItems.filter((item) => canSeeNavItem(item.href, user?.permissions ?? []));

  return (
    <nav className="flex gap-2 overflow-x-auto border-b border-slate-200 bg-white/90 px-4 py-3 xl:hidden dark:border-slate-800 dark:bg-slate-950/85">
      {visibleItems.map((item) => {
        const Icon = item.icon;

        return (
          <Link
            key={item.href}
            href={item.href}
            className="flex shrink-0 items-center gap-2 rounded-xl border border-slate-200 px-3 py-2 text-xs font-medium text-slate-600 hover:bg-blue-50 hover:text-blue-700 dark:border-slate-800 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-blue-300"
          >
            <Icon className="h-4 w-4" aria-hidden />
            {t(item.key)}
          </Link>
        );
      })}
    </nav>
  );
}
