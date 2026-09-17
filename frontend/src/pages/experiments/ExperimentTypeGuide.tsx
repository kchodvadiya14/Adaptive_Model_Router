import { Badge } from '../../components/Badge';
import { EXPERIMENT_TYPE_META, EXPERIMENT_TYPE_ORDER, ROUTER_TYPE_META, ROUTER_TYPE_ORDER, type ExperimentType, type RouterTypeId } from './format';

interface ExperimentTypeGuideProps {
  selected: ExperimentType;
  disabled?: boolean;
  onSelect: (type: ExperimentType) => void;
}

export function ExperimentTypeGuide({ selected, disabled = false, onSelect }: ExperimentTypeGuideProps) {
  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
      {EXPERIMENT_TYPE_ORDER.map((id) => {
        const meta = EXPERIMENT_TYPE_META[id];
        const isOn = id === selected;
        return (
          <button
            key={id}
            type="button"
            disabled={disabled}
            onClick={() => onSelect(id)}
            aria-pressed={isOn}
            className={`rounded-card border p-4 text-left transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/60 ${
              isOn ? 'border-brand-500/40 bg-brand-500/10' : 'border-line bg-surface-1 hover:border-line-strong'
            } disabled:cursor-not-allowed disabled:opacity-50`}
          >
            <div className="mb-2 flex items-center justify-between gap-2">
              <span className="text-sm font-medium text-ink-primary">{meta.label}</span>
              <Badge variant={isOn ? meta.badge : 'neutral'}>{isOn ? 'Selected' : 'Off'}</Badge>
            </div>
            <p className="text-xs leading-relaxed text-ink-muted">{meta.description}</p>
          </button>
        );
      })}
    </div>
  );
}

interface RouterTypeGuideProps {
  selected: string[];
  disabled?: boolean;
  onToggle: (routerType: RouterTypeId) => void;
}

export function RouterTypeGuide({ selected, disabled = false, onToggle }: RouterTypeGuideProps) {
  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
      {ROUTER_TYPE_ORDER.map((id) => {
        const meta = ROUTER_TYPE_META[id];
        const isOn = selected.includes(id);
        return (
          <button
            key={id}
            type="button"
            disabled={disabled}
            onClick={() => onToggle(id)}
            aria-pressed={isOn}
            className={`rounded-card border p-4 text-left transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/60 ${
              isOn ? 'border-brand-500/40 bg-brand-500/10' : 'border-line bg-surface-1 hover:border-line-strong'
            } disabled:cursor-not-allowed disabled:opacity-50`}
          >
            <div className="mb-2 flex items-center justify-between gap-2">
              <span className="text-sm font-medium text-ink-primary">{meta.label}</span>
              <Badge variant={isOn ? 'info' : 'neutral'}>{isOn ? 'Included' : 'Off'}</Badge>
            </div>
            <p className="text-xs leading-relaxed text-ink-muted">{meta.description}</p>
          </button>
        );
      })}
    </div>
  );
}
