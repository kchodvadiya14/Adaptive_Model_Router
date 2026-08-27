import type { ReactNode } from 'react';

interface ChartCardProps {
  title: string;
  children: ReactNode;
  emptyMessage?: string;
  isEmpty?: boolean;
}

export function ChartCard({ title, children, emptyMessage = 'No data yet.', isEmpty = false }: ChartCardProps) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-5">
      <h3 className="mb-4 text-sm font-medium text-white">{title}</h3>
      <div className="h-64">
        {isEmpty ? <p className="text-sm text-slate-500">{emptyMessage}</p> : children}
      </div>
    </div>
  );
}
