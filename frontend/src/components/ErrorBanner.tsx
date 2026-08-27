interface ErrorBannerProps {
  message: string;
  variant?: 'error' | 'warning';
}

export function ErrorBanner({ message, variant = 'error' }: ErrorBannerProps) {
  const styles =
    variant === 'warning'
      ? 'border-amber-500/30 bg-amber-500/10 text-amber-200'
      : 'border-red-500/30 bg-red-500/10 text-red-300';

  return (
    <div className={`mb-4 rounded-lg border px-4 py-3 text-sm ${styles}`}>
      {message}
    </div>
  );
}
