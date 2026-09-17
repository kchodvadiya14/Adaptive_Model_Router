export type AnalyticsPeriod = 'all' | '24h' | '7d' | '30d';

export interface PeriodOption {
  id: AnalyticsPeriod;
  label: string;
}

export const PERIOD_OPTIONS: PeriodOption[] = [
  { id: 'all', label: 'All time' },
  { id: '24h', label: 'Last 24 hours' },
  { id: '7d', label: 'Last 7 days' },
  { id: '30d', label: 'Last 30 days' },
];

export function periodLabel(period: AnalyticsPeriod): string {
  return PERIOD_OPTIONS.find((option) => option.id === period)?.label ?? 'All time';
}

/** Query params for `/api/performance/models`. Omit entirely for all-time. */
export function periodToPerformanceParams(period: AnalyticsPeriod): { since?: string; until?: string } {
  if (period === 'all') return {};

  const until = new Date();
  const ms =
    period === '24h' ? 24 * 60 * 60 * 1000 : period === '7d' ? 7 * 24 * 60 * 60 * 1000 : 30 * 24 * 60 * 60 * 1000;
  const since = new Date(until.getTime() - ms);

  return { since: since.toISOString(), until: until.toISOString() };
}
