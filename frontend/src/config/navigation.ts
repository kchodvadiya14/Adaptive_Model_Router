import {
  BarChart3,
  Bot,
  Cpu,
  Database,
  FlaskConical,
  LayoutDashboard,
  MessageSquare,
  Microscope,
  Settings,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  end?: boolean;
}

export interface NavGroup {
  label: string;
  items: NavItem[];
}

export const navGroups: NavGroup[] = [
  {
    label: 'Core',
    items: [
      { to: '/', label: 'Overview', icon: LayoutDashboard, end: true },
      { to: '/chat', label: 'Chat', icon: MessageSquare },
      { to: '/models', label: 'Models', icon: Bot },
    ],
  },
  {
    label: 'Insights',
    items: [
      { to: '/analytics', label: 'Analytics', icon: BarChart3 },
      { to: '/benchmark', label: 'Benchmark', icon: FlaskConical },
    ],
  },
  {
    label: 'Development',
    items: [
      { to: '/dataset', label: 'Dataset', icon: Database },
      { to: '/training', label: 'Training', icon: Cpu },
      { to: '/experiments', label: 'Experiments', icon: Microscope },
    ],
  },
  {
    label: 'System',
    items: [{ to: '/settings', label: 'Settings', icon: Settings }],
  },
];

export function findActiveNavItem(pathname: string): { group: string; item: NavItem } | undefined {
  for (const group of navGroups) {
    for (const item of group.items) {
      const matches = item.end ? pathname === item.to : pathname === item.to || pathname.startsWith(`${item.to}/`);
      if (matches) return { group: group.label, item };
    }
  }
  return undefined;
}
