import type { LucideIcon } from 'lucide-react';

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description: string;
}

export function EmptyState({ icon: Icon, title, description }: EmptyStateProps) {
  return (
    <div className="rounded-card border border-dashed border-line-strong bg-surface-1/60 p-12 text-center">
      <Icon className="mx-auto mb-3 h-8 w-8 text-ink-muted" />
      <h3 className="text-sm font-medium text-ink-secondary">{title}</h3>
      <p className="mt-2 text-sm text-ink-muted">{description}</p>
    </div>
  );
}
