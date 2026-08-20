type ModulePlaceholderProps = {
  title: string;
  description: string;
};

export function ModulePlaceholder({ title, description }: ModulePlaceholderProps) {
  return (
    <section className="space-y-3 rounded-2xl border border-dashed border-slate-300 bg-white p-8 dark:border-slate-700 dark:bg-slate-900">
      <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
      <p className="max-w-xl text-sm text-slate-500">{description}</p>
    </section>
  );
}
