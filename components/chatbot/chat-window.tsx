import type { ChatMessage } from "@/lib/types/chatbot";

type ChatWindowProps = {
  messages: ChatMessage[];
  loading: boolean;
  loadingText: string;
};

export function ChatWindow({ messages, loading, loadingText }: ChatWindowProps) {
  return (
    <div className="h-full min-h-[420px] space-y-3 overflow-y-auto rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
      {messages.map((message) => (
        <div key={message.id} className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}>
          <div
            className={`max-w-[85%] rounded-2xl px-3 py-2 text-sm whitespace-pre-line ${
              message.role === "user"
                ? "bg-slate-900 text-white dark:bg-slate-700"
                : "bg-slate-100 text-slate-800 dark:bg-slate-800 dark:text-slate-100"
            }`}
          >
            {message.content}
          </div>
        </div>
      ))}

      {loading ? <p className="text-xs text-slate-500">{loadingText}</p> : null}
    </div>
  );
}
