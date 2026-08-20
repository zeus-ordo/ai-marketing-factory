type ChatInputProps = {
  value: string;
  placeholder: string;
  sendLabel: string;
  disabled?: boolean;
  onChange: (value: string) => void;
  onSend: () => void;
};

export function ChatInput({ value, placeholder, sendLabel, disabled, onChange, onSend }: ChatInputProps) {
  return (
    <div className="grid gap-3 rounded-2xl border border-slate-200 bg-white p-4 md:grid-cols-[1fr_auto] dark:border-slate-800 dark:bg-slate-900">
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !disabled) {
            event.preventDefault();
            onSend();
          }
        }}
        placeholder={placeholder}
        aria-label={placeholder}
        disabled={disabled}
        className="rounded-xl border border-slate-200 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
      />
      <button
        type="button"
        onClick={onSend}
        disabled={disabled || !value.trim()}
        className="whitespace-nowrap rounded-xl bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50 dark:bg-slate-700"
      >
        {sendLabel}
      </button>
    </div>
  );
}
