import type { HTMLAttributes, ReactNode } from 'react';

type CardPadding = 'none' | 'sm' | 'md' | 'lg';

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
  padding?: CardPadding;
}

const paddingStyles: Record<CardPadding, string> = {
  none: '',
  sm: 'p-4',
  md: 'p-5',
  lg: 'p-6',
};

export function Card({ children, className = '', padding = 'md', ...rest }: CardProps) {
  return (
    <div
      className={`rounded-card border border-line bg-surface-2/60 shadow-card ${paddingStyles[padding]} ${className}`}
      {...rest}
    >
      {children}
    </div>
  );
}
