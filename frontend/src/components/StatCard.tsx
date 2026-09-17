import { Card } from './Card';

interface StatCardProps {
  label: string;
  value: string | number;
  subtext?: string;
}

export function StatCard({ label, value, subtext }: StatCardProps) {
  return (
    <Card>
      <p className="text-sm text-ink-secondary">{label}</p>
      <p className="mt-2 text-2xl font-semibold text-ink-primary">{value}</p>
      {subtext && <p className="mt-1 text-xs text-ink-muted">{subtext}</p>}
    </Card>
  );
}
