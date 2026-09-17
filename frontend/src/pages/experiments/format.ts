import type { BadgeVariant } from '../../components/Badge';

export type ExperimentType = 'final_evaluation' | 'strategy_comparison' | 'quality_floor_sweep' | 'router_comparison';

export const EXPERIMENT_TYPE_ORDER: ExperimentType[] = [
  'final_evaluation',
  'strategy_comparison',
  'quality_floor_sweep',
  'router_comparison',
];

export interface ExperimentTypeMeta {
  id: ExperimentType;
  label: string;
  description: string;
  badge: BadgeVariant;
}

export const EXPERIMENT_TYPE_META: Record<ExperimentType, ExperimentTypeMeta> = {
  final_evaluation: {
    id: 'final_evaluation',
    label: 'Final Evaluation',
    description:
      'Runs all three sections below in one job: strategy comparison, quality-floor ablation, and router comparison.',
    badge: 'info',
  },
  strategy_comparison: {
    id: 'strategy_comparison',
    label: 'Strategy Comparison',
    description: 'Compares the strategies you select (Always Strong / Always Cheap / Adaptive Router) on the same dataset.',
    badge: 'strong',
  },
  quality_floor_sweep: {
    id: 'quality_floor_sweep',
    label: 'Quality Floor Ablation',
    description: 'Runs the Adaptive Router once per quality floor you list, to see how the floor trades off cost and quality.',
    badge: 'medium',
  },
  router_comparison: {
    id: 'router_comparison',
    label: 'Router Comparison',
    description: 'Runs the Adaptive Router using each selected router implementation on the same dataset.',
    badge: 'small',
  },
};

export type RouterTypeId = 'rule_based' | 'tfidf' | 'embedding' | 'bert';

export const ROUTER_TYPE_ORDER: RouterTypeId[] = ['rule_based', 'tfidf', 'embedding', 'bert'];

export interface RouterTypeMeta {
  id: RouterTypeId;
  label: string;
  description: string;
}

export const ROUTER_TYPE_META: Record<RouterTypeId, RouterTypeMeta> = {
  rule_based: {
    id: 'rule_based',
    label: 'Rule-Based',
    description: 'Heuristic keyword/pattern rules. Always available; no trained artifact required.',
  },
  tfidf: {
    id: 'tfidf',
    label: 'TF-IDF',
    description: 'Bag-of-words classifier trained on preference data. Skipped if no trained artifact exists.',
  },
  embedding: {
    id: 'embedding',
    label: 'Embedding',
    description: 'Embedding-similarity classifier trained on preference data. Skipped if no trained artifact exists.',
  },
  bert: {
    id: 'bert',
    label: 'BERT',
    description: 'Fine-tuned BERT classifier trained on preference data. Skipped if no trained artifact exists.',
  },
};

export function experimentTypeLabel(type: string): string {
  return EXPERIMENT_TYPE_META[type as ExperimentType]?.label ?? type.replace(/_/g, ' ');
}

export function experimentTypeBadge(type: string): BadgeVariant {
  return EXPERIMENT_TYPE_META[type as ExperimentType]?.badge ?? 'neutral';
}

export function parseQualityFloors(text: string): number[] {
  return [...new Set(
    text
      .split(',')
      .map((part) => Number.parseFloat(part.trim()))
      .filter((value) => Number.isFinite(value) && value >= 0 && value <= 1),
  )].sort((a, b) => a - b);
}

export function formatConfig(config: Record<string, unknown>): string {
  const entries = Object.entries(config);
  if (entries.length === 0) return '—';
  return entries
    .map(([key, value]) => `${key}=${typeof value === 'number' ? value : String(value)}`)
    .join(' · ');
}
