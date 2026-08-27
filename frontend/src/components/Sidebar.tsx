import { NavLink } from 'react-router-dom';
import {
  BarChart3,
  Bot,
  Database,
  FlaskConical,
  LayoutDashboard,
  MessageSquare,
  Microscope,
  Settings,
  Zap,
} from 'lucide-react';
import type { HealthResponse } from '../types';

const navItems = [
  { to: '/', label: 'Overview', icon: LayoutDashboard, end: true },
  { to: '/chat', label: 'Chat', icon: MessageSquare },
  { to: '/analytics', label: 'Analytics', icon: BarChart3 },
  { to: '/models', label: 'Model Registry', icon: Bot },
  { to: '/benchmark', label: 'Benchmark', icon: FlaskConical },
  { to: '/dataset', label: 'Dataset', icon: Database },
  { to: '/training', label: 'Training', icon: LayoutDashboard },
  { to: '/experiments', label: 'Experiments', icon: Microscope },
  { to: '/settings', label: 'Settings', icon: Settings },
];

interface SidebarProps {
  health?: HealthResponse | null;
}

export function Sidebar({ health = null }: SidebarProps) {
  const healthStatus = health?.status ?? 'unknown';

  return (
    <aside className="flex h-screen w-64 flex-col border-r border-slate-800 bg-slate-900/80 backdrop-blur">
      <div className="flex items-center gap-3 border-b border-slate-800 px-6 py-5">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-600">
          <Zap className="h-5 w-5 text-white" />
        </div>
        <div>
          <h1 className="text-sm font-semibold text-white">Adaptive Model Router</h1>
          <p className="text-xs text-slate-400">AIML Final Year Project</p>
        </div>
      </div>

      <nav className="flex-1 space-y-1 px-3 py-4">
        {navItems.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors ${
                isActive
                  ? 'bg-brand-600/20 text-brand-100'
                  : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'
              }`
            }
          >
            <Icon className="h-4 w-4" />
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="border-t border-slate-800 px-6 py-4">
        <div className="flex items-center gap-2 text-xs text-slate-400">
          <span
            className={`h-2 w-2 rounded-full ${
              healthStatus === 'ok' ? 'bg-emerald-400' : 'bg-amber-400'
            }`}
          />
          Backend: {healthStatus === 'ok' ? 'Connected' : 'Checking...'}
        </div>
        <p className="mt-1 text-xs text-slate-500">
          {health ? `v${health.version} · v1.0 Final` : 'Milestone 10 — Final Evaluation'}
        </p>
      </div>
    </aside>
  );
}
