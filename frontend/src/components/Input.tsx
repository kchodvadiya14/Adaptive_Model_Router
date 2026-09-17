import { forwardRef } from 'react';
import type { InputHTMLAttributes } from 'react';

type InputProps = InputHTMLAttributes<HTMLInputElement>;

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { className = '', ...rest },
  ref,
) {
  return (
    <input
      ref={ref}
      className={`w-full rounded-control border border-line bg-surface-1 px-3 py-2 text-sm text-ink-primary placeholder:text-ink-muted focus:outline-none focus:ring-2 focus:ring-brand-500/50 disabled:opacity-50 ${className}`}
      {...rest}
    />
  );
});
