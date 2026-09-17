import { PERIOD_OPTIONS, type AnalyticsPeriod } from './period';

interface PeriodSelectorProps {
  value: AnalyticsPeriod;
  onChange: (period: AnalyticsPeriod) => void;
  disabled?: boolean;
}

export function PeriodSelector({ value, onChange, disabled }: PeriodSelectorProps) {
  return (
    <div
      className="inline-flex flex-wrap rounded-lg border border-line bg-surface-1 p-0.5"
      role="group"
      aria-label="Time period"
    >
      {PERIOD_OPTIONS.map((option) => {
        const selected = value === option.id;
        return (
          <button
            key={option.id}
            type="button"
            disabled={disabled}
            aria-pressed={selected}
            onClick={() => onChange(option.id)}
            className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors disabled:opacity-50 ${
              selected
                ? 'bg-surface-3 text-ink-primary shadow-sm'
                : 'text-ink-muted hover:text-ink-secondary'
            }`}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
