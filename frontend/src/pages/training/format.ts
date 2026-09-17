import type { BadgeVariant } from '../../components/Badge';
import type { TrainedModelInfo, TrainingJobStatus } from '../../types';

export type TrainingUIStatus = 'idle' | 'starting' | TrainingJobStatus['status'];

export const ROUTER_TYPE_LABEL: Record<TrainedModelInfo['router_type'], string> = {
  tfidf: 'TF-IDF + Logistic Regression',
  embedding: 'Embedding + Classifier',
  bert: 'BERT-style MLP',
};

export const ROUTER_TYPE_BADGE: Record<TrainedModelInfo['router_type'], BadgeVariant> = {
  tfidf: 'info',
  embedding: 'warning',
  bert: 'strong',
};

export function statusLabel(status: TrainingUIStatus): string {
  switch (status) {
    case 'idle':
      return 'Idle';
    case 'starting':
      return 'Starting training job…';
    case 'queued':
      return 'Queued';
    case 'running':
      return 'Fitting classifier on preference data…';
    case 'completed':
      return 'Completed';
    case 'failed':
      return 'Failed';
    default:
      return 'Running';
  }
}

export const STATUS_BADGE: Record<TrainingUIStatus, BadgeVariant> = {
  idle: 'neutral',
  starting: 'info',
  queued: 'info',
  running: 'info',
  completed: 'success',
  failed: 'error',
};

export function formatPercent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return `${(value * 100).toFixed(digits)}%`;
}

export function formatTimestamp(value: string | null | undefined): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export const CHART_TOOLTIP_STYLE = {
  background: '#121a2c',
  border: '1px solid #1f2740',
  borderRadius: 8,
};
export const CHART_TOOLTIP_LABEL = { color: '#f4f6fb' };
export const CHART_TOOLTIP_ITEM = { color: '#9aa4bd' };
export const CHART_AXIS_COLOR = '#707b96';
export const CHART_GRID_COLOR = '#1f2740';
