type ChatActionCardsProps = {
  title: string;
  actions: Array<{ id: string; label: string; prompt: string }>;
  disabled?: boolean;
  onSelect: (prompt: string) => void;
};

export function ChatActionCards({ title, actions, disabled, onSelect }: ChatActionCardsProps) {
  return (
    <div className="space-y-3 rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
      <p className="text-sm font-semibold text-slate-700 dark:text-slate-200">{title}</p>
      <div className="grid gap-2 md:grid-cols-2">
        {actions.map((action) => (
          <button
            key={action.id}
            type="button"
            disabled={disabled}
            onClick={() => onSelect(action.prompt)}
            className="rounded-xl border border-slate-200 px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
          >
            {action.label}
          </button>
        ))}
      </div>
    </div>
  );
}
