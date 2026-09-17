import type { ReactNode } from 'react';

export type BadgeVariant =
  | 'success'
  | 'warning'
  | 'error'
  | 'info'
  | 'neutral'
  | 'small'
  | 'medium'
  | 'strong'
  | 'closed'
  | 'half_open'
  | 'open';

interface BadgeProps {
  variant?: BadgeVariant;
  children: ReactNode;
  className?: string;
}

const variantStyles: Record<BadgeVariant, string> = {
  success: 'bg-success-500/15 text-success-300',
  warning: 'bg-warning-500/15 text-warning-300',
  error: 'bg-danger-500/15 text-danger-300',
  info: 'bg-info-500/15 text-info-300',
  neutral: 'bg-surface-3 text-ink-secondary',
  // Model tiers
  small: 'bg-success-500/15 text-success-300',
  medium: 'bg-warning-500/15 text-warning-300',
  strong: 'bg-danger-500/15 text-danger-300',
  // Circuit-breaker / health states: closed = healthy, half_open = recovering, open = broken
  closed: 'bg-success-500/15 text-success-300',
  half_open: 'bg-warning-500/15 text-warning-300',
  open: 'bg-danger-500/15 text-danger-300',
};

export function Badge({ variant = 'neutral', children, className = '' }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium capitalize ${variantStyles[variant]} ${className}`}
    >
      {children}
    </span>
  );
}
