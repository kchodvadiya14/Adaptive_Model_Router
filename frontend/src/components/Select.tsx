import { forwardRef } from 'react';
import type { SelectHTMLAttributes } from 'react';
import { ChevronDown } from 'lucide-react';

type SelectProps = SelectHTMLAttributes<HTMLSelectElement>;

export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { className = '', children, ...rest },
  ref,
) {
  return (
    <div className="relative">
      <select
        ref={ref}
        className={`w-full appearance-none rounded-control border border-line bg-surface-1 px-3 py-2 pr-8 text-sm text-ink-primary focus:outline-none focus:ring-2 focus:ring-brand-500/50 disabled:opacity-50 ${className}`}
        {...rest}
      >
        {children}
      </select>
      <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-muted" />
    </div>
  );
});
