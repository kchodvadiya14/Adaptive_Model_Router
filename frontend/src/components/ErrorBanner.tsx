interface ErrorBannerProps {
  message: string;
  variant?: 'error' | 'warning';
  className?: string;
}

export function ErrorBanner({ message, variant = 'error', className = 'mb-4' }: ErrorBannerProps) {
  const styles =
    variant === 'warning'
      ? 'border-warning-500/30 bg-warning-500/10 text-warning-300'
      : 'border-danger-500/30 bg-danger-500/10 text-danger-300';

  return <div className={`rounded-lg border px-4 py-3 text-sm ${styles} ${className}`}>{message}</div>;
}
