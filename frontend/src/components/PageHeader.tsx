import type { ReactNode } from 'react';

interface PageHeaderProps {
  title: string;
  description: string;
  action?: ReactNode;
}

export function PageHeader({ title, description, action }: PageHeaderProps) {
  return (
    <div className="mb-8 flex items-start justify-between gap-4">
      <div>
        <h2 className="text-2xl font-semibold text-ink-primary">{title}</h2>
        <p className="mt-1 text-sm text-ink-secondary">{description}</p>
      </div>
      {action}
    </div>
  );
}
