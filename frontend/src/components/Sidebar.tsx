import { useEffect, useRef } from 'react';
import { NavLink } from 'react-router-dom';
import { X, Zap } from 'lucide-react';
import { navGroups } from '../config/navigation';
import type { HealthResponse } from '../types';

interface SidebarContentProps {
  health: HealthResponse | null;
  onNavigate?: () => void;
}

function SidebarContent({ health, onNavigate }: SidebarContentProps) {
  const healthStatus = health?.status ?? 'unknown';

  return (
    <>
      <div className="flex items-center gap-3 border-b border-line px-6 py-5">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-600">
          <Zap className="h-5 w-5 text-white" />
        </div>
        <div>
          <h1 className="text-sm font-semibold text-ink-primary">Adaptive AI Gateway</h1>
          <p className="text-xs text-ink-muted">Intelligent LLM Routing</p>
        </div>
      </div>

      <nav className="flex-1 space-y-5 overflow-y-auto px-3 py-4">
        {navGroups.map((group) => (
          <div key={group.label}>
            <p className="mb-1.5 px-3 text-[11px] font-semibold uppercase tracking-wider text-ink-disabled">
              {group.label}
            </p>
            <div className="space-y-1">
              {group.items.map(({ to, label, icon: Icon, end }) => (
                <NavLink
                  key={to}
                  to={to}
                  end={end}
                  onClick={onNavigate}
                  className={({ isActive }) =>
                    `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/60 ${
                      isActive
                        ? 'bg-brand-600/20 text-brand-100'
                        : 'text-ink-secondary hover:bg-surface-3 hover:text-ink-primary'
                    }`
                  }
                >
                  <Icon className="h-4 w-4" />
                  {label}
                </NavLink>
              ))}
            </div>
          </div>
        ))}
      </nav>

      <div className="border-t border-line px-6 py-4">
        <div className="flex items-center gap-2 text-xs text-ink-secondary">
          <span className={`h-2 w-2 rounded-full ${healthStatus === 'ok' ? 'bg-success-400' : 'bg-warning-400'}`} />
          Backend: {healthStatus === 'ok' ? 'Connected' : 'Checking...'}
        </div>
        <p className="mt-1 text-xs text-ink-muted">{health ? `v${health.version}` : 'Awaiting connection'}</p>
      </div>
    </>
  );
}

interface SidebarProps {
  health?: HealthResponse | null;
  mobileOpen: boolean;
  onMobileClose: () => void;
}

export function Sidebar({ health = null, mobileOpen, onMobileClose }: SidebarProps) {
  const drawerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!mobileOpen) return;

    const previouslyFocused = document.activeElement as HTMLElement | null;
    drawerRef.current?.focus();

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onMobileClose();
    };
    document.addEventListener('keydown', handleKeyDown);

    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      previouslyFocused?.focus();
    };
  }, [mobileOpen, onMobileClose]);

  return (
    <>
      {/* Desktop: persistent sidebar */}
      <aside className="hidden h-screen w-64 flex-col border-r border-line bg-surface-1/95 backdrop-blur lg:flex">
        <SidebarContent health={health} />
      </aside>

      {/* Mobile/tablet: overlay drawer */}
      {mobileOpen && (
        <div className="fixed inset-0 z-50 flex lg:hidden">
          <div className="absolute inset-0 bg-overlay" onClick={onMobileClose} aria-hidden="true" />
          <div
            ref={drawerRef}
            role="dialog"
            aria-modal="true"
            aria-label="Navigation menu"
            tabIndex={-1}
            className="relative flex h-full w-72 max-w-[85vw] flex-col border-r border-line bg-surface-1 shadow-modal focus:outline-none"
          >
            <button
              type="button"
              onClick={onMobileClose}
              aria-label="Close navigation menu"
              className="absolute right-3 top-4 text-ink-muted transition-colors hover:text-ink-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/60"
            >
              <X className="h-5 w-5" />
            </button>
            <SidebarContent health={health} onNavigate={onMobileClose} />
          </div>
        </div>
      )}
    </>
  );
}
