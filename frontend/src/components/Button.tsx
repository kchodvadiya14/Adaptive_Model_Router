import { forwardRef } from 'react';
import type { ButtonHTMLAttributes } from 'react';
import { Loader2 } from 'lucide-react';

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger';
export type ButtonSize = 'sm' | 'md';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
}

const base =
  'inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/60 focus-visible:ring-offset-2 focus-visible:ring-offset-surface-0 disabled:cursor-not-allowed disabled:opacity-50';

const variantStyles: Record<ButtonVariant, string> = {
  primary: 'bg-brand-600 text-white hover:bg-brand-500 active:bg-brand-700',
  secondary: 'border border-line bg-surface-2 text-ink-primary hover:bg-surface-3',
  ghost: 'text-ink-secondary hover:bg-surface-2 hover:text-ink-primary',
  danger: 'bg-danger-600 text-white hover:bg-danger-500 active:bg-danger-700',
};

const sizeStyles: Record<ButtonSize, string> = {
  sm: 'px-3 py-1.5 text-xs',
  md: 'px-4 py-2 text-sm',
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'primary', size = 'md', loading = false, disabled, className = '', children, ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      disabled={disabled || loading}
      className={`${base} ${variantStyles[variant]} ${sizeStyles[size]} ${className}`}
      {...rest}
    >
      {loading && <Loader2 className="h-4 w-4 animate-spin" />}
      {children}
    </button>
  );
});
