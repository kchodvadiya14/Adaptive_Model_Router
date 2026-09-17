import type { BadgeVariant } from '../../components/Badge';
import type { BenchmarkReport, BenchmarkStrategy } from '../../types';

export const STRATEGY_ORDER: BenchmarkStrategy[] = [
  'always_strong',
  'always_cheap',
  'adaptive_router',
];

export interface StrategyMeta {
  id: BenchmarkStrategy;
  label: string;
  short: string;
  description: string;
  color: string;
  badge: BadgeVariant;
}

export const STRATEGY_META: Record<BenchmarkStrategy, StrategyMeta> = {
  always_strong: {
    id: 'always_strong',
    label: 'Always Strong',
    short: 'Strong',
    description:
      'Every prompt is sent to the primary strong-tier model. This is the quality baseline and is typically the most expensive strategy.',
    color: '#f43f5e',
    badge: 'strong',
  },
  always_cheap: {
    id: 'always_cheap',
    label: 'Always Cheap',
    short: 'Cheap',
    description:
      'Every prompt is sent to the primary small-tier model. This is the cost baseline; quality depends entirely on the cheap model.',
    color: '#10b981',
    badge: 'small',
  },
  adaptive_router: {
    id: 'adaptive_router',
    label: 'Adaptive Router',
    short: 'Adaptive',
    description:
      'The router chooses a model per prompt using the configured quality floor, trading off cost and quality instead of pinning a single tier.',
    color: '#6366f1',
    badge: 'info',
  },
};

export function strategyLabel(strategy: string): string {
  return STRATEGY_META[strategy as BenchmarkStrategy]?.label ?? strategy.replace(/_/g, ' ');
}

export function strategyColor(strategy: string): string {
  return STRATEGY_META[strategy as BenchmarkStrategy]?.color ?? '#818cf8';
}

export function strategyBadge(strategy: string): BadgeVariant {
  return STRATEGY_META[strategy as BenchmarkStrategy]?.badge ?? 'neutral';
}

export function formatPercent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return `${(value * 100).toFixed(digits)}%`;
}

export function formatMs(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return value >= 1000 ? `${(value / 1000).toFixed(2)} s` : `${value.toFixed(0)} ms`;
}

export function formatCost(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  if (value === 0) return '$0.00';
  return `$${value.toFixed(value < 0.01 ? 6 : 4)}`;
}

export function formatTimestamp(value: string | null | undefined): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export interface ParsedSample {
  prompt_id: string;
  prompt: string;
  selected_model: string;
  tier: string;
  quality: number | null;
  cost: number | null;
  latency_ms: number | null;
}

function asNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function asString(value: unknown, fallback = '—'): string {
  return typeof value === 'string' && value.length > 0 ? value : fallback;
}

export function parseSample(raw: Record<string, unknown>): ParsedSample {
  return {
    prompt_id: asString(raw.prompt_id),
    prompt: asString(raw.prompt, ''),
    selected_model: asString(raw.selected_model),
    tier: asString(raw.tier),
    quality: asNumber(raw.quality),
    cost: asNumber(raw.cost),
    latency_ms: asNumber(raw.latency_ms),
  };
}

export interface ChartRow {
  strategy: string;
  name: string;
  color: string;
  quality: number;
  averageCost: number;
  averageLatency: number;
  p50Latency: number;
  p95Latency: number;
  costReduction: number;
  qualityRetention: number;
  routingAccuracy: number;
  strongUsage: number;
}

export function toChartRows(report: BenchmarkReport): ChartRow[] {
  return report.strategies.map((item) => ({
    strategy: item.strategy,
    name: strategyLabel(item.strategy),
    color: strategyColor(item.strategy),
    quality: Number((item.metrics.average_quality * 100).toFixed(1)),
    averageCost: item.metrics.average_cost,
    averageLatency: item.metrics.average_latency_ms,
    p50Latency: item.metrics.p50_latency_ms,
    p95Latency: item.metrics.p95_latency_ms,
    costReduction: Number((item.metrics.cost_reduction * 100).toFixed(1)),
    qualityRetention: Number((item.metrics.quality_retention * 100).toFixed(1)),
    routingAccuracy: Number((item.metrics.routing_accuracy * 100).toFixed(1)),
    strongUsage: Number((item.metrics.strong_model_usage * 100).toFixed(1)),
  }));
}

function uniqueExtreme<T>(
  items: T[],
  key: (item: T) => number,
  mode: 'min' | 'max',
  epsilon = 1e-12,
): T | null {
  if (items.length === 0) return null;
  const values = items.map(key);
  const extreme = mode === 'min' ? Math.min(...values) : Math.max(...values);
  const winners = items.filter((item) => Math.abs(key(item) - extreme) <= epsilon);
  return winners.length === 1 ? winners[0] : null;
}

const RELATIVE_COST_THRESHOLD = 0.005;
const QUALITY_THRESHOLD = 0.005;

export function buildObservations(report: BenchmarkReport): string[] {
  const labeled = report.strategies.map((item) => ({
    strategy: item.strategy,
    label: strategyLabel(item.strategy),
    metrics: item.metrics,
  }));

  if (labeled.length === 0) return [];

  if (labeled.length === 1) {
    const only = labeled[0];
    return [
      `This run evaluated only ${only.label}: ${only.metrics.total_requests} requests, average quality ${formatPercent(only.metrics.average_quality)}, average cost ${formatCost(only.metrics.average_cost)}, average latency ${formatMs(only.metrics.average_latency_ms)}.`,
    ];
  }

  const observations: string[] = [];
  const cheapest = uniqueExtreme(labeled, (s) => s.metrics.average_cost, 'min');
  const highestQuality = uniqueExtreme(labeled, (s) => s.metrics.average_quality, 'max');
  const fastest = uniqueExtreme(labeled, (s) => s.metrics.average_latency_ms, 'min', 0.5);
  const bestRetention = uniqueExtreme(labeled, (s) => s.metrics.quality_retention, 'max');
  const bestReduction = uniqueExtreme(labeled, (s) => s.metrics.cost_reduction, 'max');

  if (cheapest) {
    observations.push(
      `${cheapest.label} had the lowest average cost in this run (${formatCost(cheapest.metrics.average_cost)}).`,
    );
  }
  if (highestQuality) {
    observations.push(
      `${highestQuality.label} had the highest average quality in this run (${formatPercent(highestQuality.metrics.average_quality)}).`,
    );
  }
  if (fastest) {
    observations.push(
      `${fastest.label} had the lowest average latency in this run (${formatMs(fastest.metrics.average_latency_ms)}).`,
    );
  }
  if (bestRetention && bestRetention.strategy !== highestQuality?.strategy) {
    observations.push(
      `${bestRetention.label} retained ${formatPercent(bestRetention.metrics.quality_retention)} of the strong-model quality baseline.`,
    );
  }
  if (bestReduction) {
    observations.push(
      `${bestReduction.label} recorded the largest cost reduction versus the strong-model cost baseline (${formatPercent(bestReduction.metrics.cost_reduction)}).`,
    );
  }

  const adaptive = labeled.find((s) => s.strategy === 'adaptive_router');
  const strong = labeled.find((s) => s.strategy === 'always_strong');
  const cheap = labeled.find((s) => s.strategy === 'always_cheap');

  if (adaptive && strong && strong.metrics.average_cost > 0) {
    const relCost = (strong.metrics.average_cost - adaptive.metrics.average_cost) / strong.metrics.average_cost;
    if (relCost >= RELATIVE_COST_THRESHOLD) {
      observations.push(
        `Adaptive Router's average cost was ${formatPercent(relCost)} lower than Always Strong (${formatCost(adaptive.metrics.average_cost)} vs ${formatCost(strong.metrics.average_cost)}).`,
      );
    } else if (relCost <= -RELATIVE_COST_THRESHOLD) {
      observations.push(
        `Adaptive Router's average cost was ${formatPercent(-relCost)} higher than Always Strong (${formatCost(adaptive.metrics.average_cost)} vs ${formatCost(strong.metrics.average_cost)}).`,
      );
    }

    const qualityGap = adaptive.metrics.average_quality - strong.metrics.average_quality;
    if (qualityGap <= -QUALITY_THRESHOLD) {
      observations.push(
        `Adaptive Router average quality was ${formatPercent(strong.metrics.average_quality - adaptive.metrics.average_quality)} below Always Strong (${formatPercent(adaptive.metrics.average_quality)} vs ${formatPercent(strong.metrics.average_quality)}).`,
      );
    } else if (qualityGap >= QUALITY_THRESHOLD) {
      observations.push(
        `Adaptive Router average quality was ${formatPercent(qualityGap)} above Always Strong (${formatPercent(adaptive.metrics.average_quality)} vs ${formatPercent(strong.metrics.average_quality)}).`,
      );
    }
  }

  if (adaptive && cheap) {
    const qualityGap = adaptive.metrics.average_quality - cheap.metrics.average_quality;
    if (qualityGap >= QUALITY_THRESHOLD) {
      observations.push(
        `Adaptive Router average quality was ${formatPercent(qualityGap)} higher than Always Cheap (${formatPercent(adaptive.metrics.average_quality)} vs ${formatPercent(cheap.metrics.average_quality)}).`,
      );
    } else if (qualityGap <= -QUALITY_THRESHOLD) {
      observations.push(
        `Adaptive Router average quality was ${formatPercent(-qualityGap)} lower than Always Cheap (${formatPercent(adaptive.metrics.average_quality)} vs ${formatPercent(cheap.metrics.average_quality)}).`,
      );
    }
    if (cheap.metrics.average_cost > 0) {
      const relCost = (adaptive.metrics.average_cost - cheap.metrics.average_cost) / cheap.metrics.average_cost;
      if (relCost >= RELATIVE_COST_THRESHOLD) {
        observations.push(
          `Always Cheap remained cheaper on average than Adaptive Router (${formatCost(cheap.metrics.average_cost)} vs ${formatCost(adaptive.metrics.average_cost)}).`,
        );
      }
    }
  }

  const unique = [...new Set(observations)];
  if (unique.length === 0) {
    return [
      'This run did not show a material difference between strategies on average cost, quality, or latency.',
    ];
  }
  return unique.slice(0, 6);
}

