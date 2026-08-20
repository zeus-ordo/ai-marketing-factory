"use client";

import { MessageSquare, X } from "lucide-react";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { ChatbotPanel } from "@/components/chatbot/chatbot-panel";
import { useI18n } from "@/lib/i18n/context";

export function ChatbotDock() {
  const pathname = usePathname();
  const { t } = useI18n();
  const [open, setOpen] = useState(false);

  if (pathname?.startsWith("/auth") || pathname === "/chatbot") return null;

  return (
    <>
      <aside className="sticky top-[73px] hidden h-[calc(100vh-73px)] w-[380px] shrink-0 border-l border-slate-200 bg-white/95 p-4 shadow-xl backdrop-blur lg:flex dark:border-slate-800 dark:bg-slate-950/95">
        <div className="min-h-0 w-full">
          <ChatbotPanel compact />
        </div>
      </aside>

      {!open ? (
      <button
        onClick={() => setOpen(true)}
        className="fixed bottom-5 right-5 z-50 flex items-center gap-2 rounded-full bg-blue-600 px-4 py-3 text-sm font-semibold text-white shadow-xl ring-4 ring-blue-100 hover:bg-blue-700 lg:hidden dark:ring-blue-950"
      >
        <MessageSquare className="h-4 w-4" />
        {t("nav.chatbot")}
      </button>
      ) : (
        <aside className="fixed bottom-4 right-4 top-20 z-50 flex w-[380px] max-w-[calc(100vw-2rem)] rounded-2xl border border-slate-200 bg-white/95 p-4 shadow-2xl backdrop-blur lg:hidden dark:border-slate-800 dark:bg-slate-950/95">
          <button
            onClick={() => setOpen(false)}
            className="absolute right-3 top-3 rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800 dark:hover:text-slate-200"
            aria-label={t("chatbot.closeDock")}
          >
            <X className="h-4 w-4" />
          </button>
          <div className="min-h-0 w-full pt-2">
            <ChatbotPanel compact />
          </div>
        </aside>
      )}
    </>
  );
}
