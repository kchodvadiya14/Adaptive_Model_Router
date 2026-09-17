import { Menu } from 'lucide-react';
import { Badge } from './Badge';
import type { HealthResponse } from '../types';

interface HeaderProps {
  title: string;
  group?: string;
  health: HealthResponse | null;
  onMenuClick: () => void;
}

export function Header({ title, group, health, onMenuClick }: HeaderProps) {
  const isOnline = health?.status === 'ok';

  return (
    <header className="sticky top-0 z-30 flex items-center justify-between border-b border-line bg-surface-1/80 px-4 py-3.5 backdrop-blur sm:px-6 lg:px-8">
      <div className="flex items-center gap-3 min-w-0">
        <button
          type="button"
          onClick={onMenuClick}
          aria-label="Open navigation menu"
          className="-ml-1 flex h-9 w-9 items-center justify-center rounded-lg text-ink-secondary transition-colors hover:bg-surface-3 hover:text-ink-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/60 lg:hidden"
        >
          <Menu className="h-5 w-5" />
        </button>
        <div className="min-w-0 truncate text-sm">
          {group && <span className="text-ink-muted">{group} / </span>}
          <span className="font-medium text-ink-primary">{title}</span>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <Badge variant={isOnline ? 'success' : 'warning'} className="hidden sm:inline-flex">
          <span className={`mr-1.5 h-1.5 w-1.5 rounded-full ${isOnline ? 'bg-success-400' : 'bg-warning-400'}`} />
          {isOnline ? 'Gateway Online' : 'Connecting…'}
        </Badge>
        <span
          className={`h-2 w-2 rounded-full sm:hidden ${isOnline ? 'bg-success-400' : 'bg-warning-400'}`}
          aria-label={isOnline ? 'Gateway online' : 'Connecting'}
        />
      </div>
    </header>
  );
}
