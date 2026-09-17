import { Lightbulb } from 'lucide-react';
import { Card } from '../../components/Card';
import type { BenchmarkReport } from '../../types';
import { buildObservations, formatPercent, formatTimestamp } from './format';

interface InterpretationProps {
  report: BenchmarkReport;
}

export function Interpretation({ report }: InterpretationProps) {
  const observations = buildObservations(report);
  if (observations.length === 0) return null;

  return (
    <Card>
      <div className="mb-3 flex items-center gap-2">
        <Lightbulb className="h-4 w-4 text-warning-400" />
        <h3 className="text-sm font-medium text-ink-primary">What this benchmark tells you</h3>
      </div>
      <p className="mb-3 text-xs text-ink-muted">
        Observations from this run only · quality floor {formatPercent(report.quality_floor, 0)} ·{' '}
        {formatTimestamp(report.created_at)}
      </p>
      <ul className="space-y-2">
        {observations.map((line) => (
          <li key={line} className="flex gap-2 text-sm leading-relaxed text-ink-secondary">
            <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-brand-400" />
            {line}
          </li>
        ))}
      </ul>
    </Card>
  );
}
