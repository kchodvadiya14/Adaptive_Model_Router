import type { BadgeVariant } from '../../components/Badge';
import type { CircuitState, ModelMetadata } from '../../types';

export function formatPercent(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return `${(value * 100).toFixed(digits)}%`;
}

export function formatMs(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return value >= 1000 ? `${(value / 1000).toFixed(2)}s` : `${value.toFixed(0)}ms`;
}

export function formatCost(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  if (value === 0) return '$0.00';
  return `$${value.toFixed(value < 0.01 ? 6 : 2)}`;
}

export function formatCountdown(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || seconds <= 0) return '—';
  if (seconds < 60) return `${Math.ceil(seconds)}s`;
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.ceil(seconds % 60);
  return `${minutes}m ${remainder}s`;
}

export function formatTimestamp(value: string | null | undefined): string {
  if (!value) return 'Never';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export const HEALTH_LABEL: Record<CircuitState, string> = {
  closed: 'Healthy',
  open: 'Unavailable',
  half_open: 'Testing recovery',
};

export const HEALTH_BADGE_VARIANT: Record<CircuitState, BadgeVariant> = {
  closed: 'closed',
  open: 'open',
  half_open: 'half_open',
};

/** Mirrors the backend's ModelRegistry.get_primary_model_for_tier: the cheapest
 * enabled model in a tier is the one routing actually sends traffic to. */
export function isPrimaryForTier(model: ModelMetadata, allModels: ModelMetadata[]): boolean {
  const sameTierEnabled = allModels.filter((candidate) => candidate.tier === model.tier && candidate.enabled);
  if (sameTierEnabled.length === 0) return false;
  const cheapest = sameTierEnabled.reduce((min, candidate) =>
    candidate.input_cost_per_1m_tokens < min.input_cost_per_1m_tokens ? candidate : min,
  );
  return cheapest.id === model.id;
}
