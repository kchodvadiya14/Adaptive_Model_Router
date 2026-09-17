import { Badge } from '../../components/Badge';
import { STRATEGY_META, STRATEGY_ORDER } from './format';
import type { BenchmarkStrategy } from '../../types';

interface StrategyGuideProps {
  selected: BenchmarkStrategy[];
  disabled?: boolean;
  onToggle: (strategy: BenchmarkStrategy) => void;
}

export function StrategyGuide({ selected, disabled = false, onToggle }: StrategyGuideProps) {
  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
      {STRATEGY_ORDER.map((id) => {
        const meta = STRATEGY_META[id];
        const isOn = selected.includes(id);
        return (
          <button
            key={id}
            type="button"
            disabled={disabled}
            onClick={() => onToggle(id)}
            aria-pressed={isOn}
            className={`rounded-card border p-4 text-left transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/60 ${
              isOn
                ? 'border-brand-500/40 bg-brand-500/10'
                : 'border-line bg-surface-1 hover:border-line-strong'
            } disabled:cursor-not-allowed disabled:opacity-50`}
          >
            <div className="mb-2 flex items-center justify-between gap-2">
              <span className="flex items-center gap-2 text-sm font-medium text-ink-primary">
                <span className="h-2 w-2 rounded-full" style={{ backgroundColor: meta.color }} />
                {meta.label}
              </span>
              <Badge variant={isOn ? meta.badge : 'neutral'}>{isOn ? 'Included' : 'Off'}</Badge>
            </div>
            <p className="text-xs leading-relaxed text-ink-muted">{meta.description}</p>
          </button>
        );
      })}
    </div>
  );
}
