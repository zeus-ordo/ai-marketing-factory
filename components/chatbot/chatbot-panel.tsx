"use client";

import { useMemo, useState } from "react";
import { ChatActionCards } from "@/components/chatbot/chat-action-cards";
import { ChatInput } from "@/components/chatbot/chat-input";
import { ChatWindow } from "@/components/chatbot/chat-window";
import { useI18n } from "@/lib/i18n/context";
import type { ChatContext, ChatExecuteResponse, ChatMessage } from "@/lib/types/chatbot";

type Props = {
  compact?: boolean;
};

export function ChatbotPanel({ compact = false }: Props) {
  const { t, locale } = useI18n();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [chatContext, setChatContext] = useState<ChatContext>({});
  const [error, setError] = useState<string | null>(null);

  const quickActions = useMemo(
    () => [
      { id: "list", label: t("chatbot.quickActions.listCampaigns"), prompt: t("chatbot.quickActions.listCampaignsPrompt") },
      { id: "tasks", label: t("chatbot.quickActions.listTasks"), prompt: t("chatbot.quickActions.listTasksPrompt") },
      { id: "references", label: t("chatbot.quickActions.listReferences"), prompt: t("chatbot.quickActions.listReferencesPrompt") },
      { id: "review", label: t("chatbot.quickActions.listReviewQueue"), prompt: t("chatbot.quickActions.listReviewQueuePrompt") },
      { id: "validation", label: t("chatbot.quickActions.listValidationResults"), prompt: t("chatbot.quickActions.listValidationResultsPrompt") },
    ],
    [t],
  );

  async function sendMessage(rawMessage: string) {
    const message = rawMessage.trim();
    if (!message || busy) return;

    const now = new Date().toISOString();
    setMessages((prev) => [...prev, { id: `${now}-user`, role: "user", content: message, createdAt: now }]);
    setInput("");
    setError(null);
    setBusy(true);

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 60_000);

    try {
      const response = await fetch("/api/chat/execute", {
        method: "POST",
        headers: buildChatHeaders(),
        body: JSON.stringify({ message, locale, context: chatContext }),
        signal: controller.signal,
      });

      clearTimeout(timeout);

      if (!response.ok) {
        const contentType = response.headers.get("content-type") ?? "";
        if (contentType.includes("application/json")) {
          const payload = (await response.json()) as { detail?: unknown };
          if (typeof payload.detail === "string" && payload.detail.trim()) throw new Error(payload.detail);
        }
        const text = await response.text();
        throw new Error(text || t("chatbot.executeFailed"));
      }

      const data = (await response.json()) as ChatExecuteResponse;
      setChatContext(data.context);
      const assistantContent = data.followUp.length ? `${data.reply}\n\n${data.followUp.join("\n")}` : data.reply;
      setMessages((prev) => [
        ...prev,
        { id: `${new Date().toISOString()}-assistant`, role: "assistant", content: assistantContent, createdAt: new Date().toISOString() },
      ]);
    } catch (err) {
      clearTimeout(timeout);
      if (err instanceof Error && err.name === "AbortError") {
        setError(t("chatbot.requestTimeout"));
      } else {
        setError(err instanceof Error ? err.message : t("chatbot.executeFailed"));
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="flex h-full flex-col gap-4">
      <header>
        <h1 className={compact ? "text-base font-semibold tracking-tight" : "text-2xl font-semibold tracking-tight"}>{t("chatbot.title")}</h1>
        {!compact ? <p className="text-sm text-slate-500">{t("chatbot.subtitle")}</p> : null}
      </header>

      {error ? <p className="rounded-xl bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</p> : null}

      {chatContext.pendingActionTokenExpired ? (
        <p className="rounded-xl bg-rose-50 px-3 py-2 text-sm text-rose-700">
          {t("chatbot.pendingActionExpired")}
        </p>
      ) : chatContext.pendingAction ? (
        <p className="rounded-xl bg-amber-50 px-3 py-2 text-sm text-amber-700">
          {t("chatbot.pendingAction", {
            type: chatContext.pendingAction.type,
            target: chatContext.pendingAction.referenceId ?? chatContext.pendingAction.reviewId ?? chatContext.pendingAction.campaignId ?? "-",
          })}
          {chatContext.pendingAction.nonce ? ` ${t("chatbot.pendingActionCode", { code: chatContext.pendingAction.nonce })}` : ""}
        </p>
      ) : null}

      {!compact ? (
        <ChatActionCards
          title={t("chatbot.quickActions.title")}
          actions={quickActions}
          disabled={busy}
          onSelect={(prompt) => {
            setInput(prompt);
            void sendMessage(prompt);
          }}
        />
      ) : null}

      {/* ChatWindow takes remaining space, input sticks to bottom */}
      <div className="min-h-0 flex-1 overflow-hidden">
        <ChatWindow messages={messages} loading={busy} loadingText={t("chatbot.executing")} />
      </div>

      <ChatInput
        value={input}
        onChange={setInput}
        onSend={() => void sendMessage(input)}
        placeholder={t("chatbot.inputPlaceholder")}
        sendLabel={t("chatbot.send")}
        disabled={busy}
      />
    </section>
  );
}

function buildChatHeaders(): Record<string, string> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const actorToken = getCookieValue("chat_actor_token");
  if (actorToken) headers["x-chat-actor-token"] = actorToken;
  const accessToken = typeof window !== "undefined" ? localStorage.getItem("access_token") : null;
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
  return headers;
}

function getCookieValue(name: string): string {
  if (typeof document === "undefined") return "";
  const target = `${name}=`;
  for (const rawPart of document.cookie.split(";")) {
    const part = rawPart.trim();
    if (part.startsWith(target)) return decodeURIComponent(part.slice(target.length));
  }
  return "";
}
