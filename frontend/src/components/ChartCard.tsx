import type { ReactNode } from 'react';
import { Card } from './Card';

interface ChartCardProps {
  title: string;
  children: ReactNode;
  emptyMessage?: string;
  isEmpty?: boolean;
}

export function ChartCard({ title, children, emptyMessage = 'No data yet.', isEmpty = false }: ChartCardProps) {
  return (
    <Card>
      <h3 className="mb-4 text-sm font-medium text-ink-primary">{title}</h3>
      <div className="h-64">
        {isEmpty ? <p className="text-sm text-ink-muted">{emptyMessage}</p> : children}
      </div>
    </Card>
  );
}
