import type { LucideIcon } from 'lucide-react';

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description: string;
}

export function EmptyState({ icon: Icon, title, description }: EmptyStateProps) {
  return (
    <div className="rounded-xl border border-dashed border-slate-700 bg-slate-900/40 p-12 text-center">
      <Icon className="mx-auto mb-3 h-8 w-8 text-slate-500" />
      <h3 className="text-sm font-medium text-slate-300">{title}</h3>
      <p className="mt-2 text-sm text-slate-500">{description}</p>
    </div>
  );
}
