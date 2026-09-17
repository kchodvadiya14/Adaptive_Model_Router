import type { BadgeVariant } from '../../components/Badge';
import type { PreferenceRecord } from '../../types';

export function formatPercent(value: number | null | undefined, digits = 0): string {
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

export function formatTaskType(taskType: string): string {
  return taskType.replace(/_/g, ' ');
}

export function shortPath(path: string): string {
  return path.split('/').pop() ?? path;
}

export const TIER_BADGE: Record<'small' | 'medium' | 'strong', BadgeVariant> = {
  small: 'small',
  medium: 'medium',
  strong: 'strong',
};

export const EVAL_SOURCE_BADGE: Record<string, BadgeVariant> = {
  judge: 'info',
  human: 'success',
  mixed: 'warning',
};

export const EVAL_SOURCE_LABEL: Record<string, string> = {
  judge: 'Judge-labeled',
  human: 'Human-reviewed',
  mixed: 'Judge + human',
};

export interface DatasetBreakdown {
  taskTypes: Array<{ key: string; count: number }>;
  preferredModel: Record<'small' | 'medium' | 'strong', number>;
  evaluationSource: Record<string, number>;
}

/** Computed once from a dataset's full record set — never a partial page — so counts
 * always describe the whole dataset, not just whatever is currently displayed. */
export function computeBreakdown(records: PreferenceRecord[]): DatasetBreakdown {
  const taskTypeCounts = new Map<string, number>();
  const preferredModel: DatasetBreakdown['preferredModel'] = { small: 0, medium: 0, strong: 0 };
  const evaluationSource: Record<string, number> = {};

  for (const record of records) {
    taskTypeCounts.set(record.task_type, (taskTypeCounts.get(record.task_type) ?? 0) + 1);
    preferredModel[record.preferred_model] += 1;
    evaluationSource[record.evaluation_source] = (evaluationSource[record.evaluation_source] ?? 0) + 1;
  }

  const taskTypes = Array.from(taskTypeCounts.entries())
    .map(([key, count]) => ({ key, count }))
    .sort((a, b) => b.count - a.count);

  return { taskTypes, preferredModel, evaluationSource };
}
