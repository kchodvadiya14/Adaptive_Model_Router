import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  BarChart3,
  Clock,
  RefreshCw,
  Route,
  Wallet,
} from 'lucide-react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { Badge } from '../components/Badge';
import { Button } from '../components/Button';
import { Card } from '../components/Card';
import { ChartCard } from '../components/ChartCard';
import { EmptyState } from '../components/EmptyState';
import { ErrorBanner } from '../components/ErrorBanner';
import { PageHeader } from '../components/PageHeader';
import { StatCard } from '../components/StatCard';
import { Table, TableContainer, TBody, Td, Th, THead, Tr } from '../components/Table';
import { fetchMetrics, fetchModelPerformance, fetchModels, fetchUsage } from '../services/api';
import type {
  MetricsSummary,
  ModelMetadata,
  ModelPerformance,
  UsageBreakdownEntry,
  UsageSummary,
} from '../types';
import { formatCost, formatMs, formatPercent } from './models/format';
import { aggregatePerformance, isModelTier, lookupModel, usageByTier } from './analytics/aggregates';
import { PeriodSelector } from './analytics/PeriodSelector';
import { periodLabel, periodToPerformanceParams, type AnalyticsPeriod } from './analytics/period';

type UsageGroup = 'model' | 'tier' | 'user' | 'tag';

const TIER_BAR_COLORS: Record<string, string> = {
  small: '#34d399',
  medium: '#fbbf24',
  strong: '#fb7185',
};

const CHART_TOOLTIP_STYLE = {
  background: '#121a2c',
  border: '1px solid #1f2740',
  borderRadius: 8,
};

const AXIS_TICK = { fill: '#707b96', fontSize: 11 };

function SkeletonBlock({ className = '' }: { className?: string }) {
  return <div className={`animate-pulse rounded-lg bg-surface-3 ${className}`} />;
}

function SkeletonRows({ rows = 4, cols = 6 }: { rows?: number; cols?: number }) {
  return (
    <TableContainer>
      <Table>
        <TBody>
          {Array.from({ length: rows }).map((_, rowIndex) => (
            <Tr key={rowIndex} className="hover:bg-transparent">
              {Array.from({ length: cols }).map((__, colIndex) => (
                <Td key={colIndex}>
                  <SkeletonBlock className="h-4 w-full max-w-[120px]" />
                </Td>
              ))}
            </Tr>
          ))}
        </TBody>
      </Table>
    </TableContainer>
  );
}

function SourceBadge({ children }: { children: string }) {
  return (
    <span className="rounded-full bg-surface-3 px-2.5 py-1 text-[11px] font-medium text-ink-secondary">{children}</span>
  );
}

function SectionHeading({
  title,
  badge,
  hint,
}: {
  title: string;
  badge: string;
  hint?: string;
}) {
  return (
    <div className="mb-3 flex flex-wrap items-center gap-2">
      <h3 className="text-sm font-medium text-ink-primary">{title}</h3>
      <SourceBadge>{badge}</SourceBadge>
      {hint && <p className="text-xs text-ink-muted">{hint}</p>}
    </div>
  );
}

function truncateLabel(value: string, max = 16): string {
  return value.length > max ? `${value.slice(0, max - 1)}…` : value;
}

function chartDataFromRecord(record: Record<string, number>): { name: string; value: number }[] {
  return Object.entries(record)
    .map(([name, value]) => ({ name, value }))
    .sort((a, b) => b.value - a.value);
}

export function AnalyticsPage() {
  const [period, setPeriod] = useState<AnalyticsPeriod>('all');
  const [usageGroup, setUsageGroup] = useState<UsageGroup>('model');

  const [metrics, setMetrics] = useState<MetricsSummary | null>(null);
  const [metricsError, setMetricsError] = useState<string | null>(null);
  const [metricsLoading, setMetricsLoading] = useState(true);

  const [performance, setPerformance] = useState<ModelPerformance[]>([]);
  const [performanceError, setPerformanceError] = useState<string | null>(null);
  const [performanceLoading, setPerformanceLoading] = useState(true);

  const [usage, setUsage] = useState<UsageSummary | null>(null);
  const [usageError, setUsageError] = useState<string | null>(null);
  const [usageLoading, setUsageLoading] = useState(true);

  const [models, setModels] = useState<ModelMetadata[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const performanceRequestId = useRef(0);

  const loadMetricsAndUsage = useCallback(async () => {
    setMetricsLoading(true);
    setUsageLoading(true);

    const [metricsResult, usageResult, modelsResult] = await Promise.allSettled([
      fetchMetrics(),
      fetchUsage(),
      fetchModels(),
    ]);

    if (metricsResult.status === 'fulfilled') {
      setMetrics(metricsResult.value);
      setMetricsError(null);
    } else {
      setMetrics(null);
      setMetricsError('Routing metrics unavailable. Totals from the routing log could not be loaded.');
    }

    if (usageResult.status === 'fulfilled') {
      setUsage(usageResult.value);
      setUsageError(null);
    } else {
      setUsage(null);
      setUsageError('Usage breakdown unavailable. /api/usage could not be loaded.');
    }

    setModels(modelsResult.status === 'fulfilled' ? modelsResult.value : []);
    setMetricsLoading(false);
    setUsageLoading(false);
  }, []);

  const loadPerformance = useCallback(async (selectedPeriod: AnalyticsPeriod) => {
    const requestId = ++performanceRequestId.current;
    setPerformanceLoading(true);
    try {
      const params = periodToPerformanceParams(selectedPeriod);
      const report = await fetchModelPerformance(
        Object.keys(params).length > 0 ? params : undefined,
      );
      if (requestId !== performanceRequestId.current) return;
      setPerformance(report.models);
      setPerformanceError(null);
    } catch {
      if (requestId !== performanceRequestId.current) return;
      setPerformance([]);
      setPerformanceError(
        'Model performance unavailable. Success, quality-failure, and period-filtered KPIs cannot be shown.',
      );
    } finally {
      if (requestId === performanceRequestId.current) {
        setPerformanceLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    void loadMetricsAndUsage();
  }, [loadMetricsAndUsage]);

  useEffect(() => {
    void loadPerformance(period).then(() => setLastUpdated(new Date()));
  }, [loadPerformance, period]);

  const refreshAll = async () => {
    setRefreshing(true);
    await Promise.all([loadMetricsAndUsage(), loadPerformance(period)]);
    setLastUpdated(new Date());
    setRefreshing(false);
  };

  const aggregates = useMemo(() => aggregatePerformance(performance), [performance]);
  const selectedPeriodLabel = periodLabel(period);
  const initialLoading = metricsLoading && performanceLoading && usageLoading;

  const modelChartData = metrics ? chartDataFromRecord(metrics.requests_by_model) : [];
  const taskChartData = metrics ? chartDataFromRecord(metrics.requests_by_task) : [];
  const tierChartData = metrics ? chartDataFromRecord(metrics.requests_by_tier) : [];

  const volumeChartData = useMemo(
    () =>
      [...performance]
        .sort((a, b) => b.request_count - a.request_count)
        .map((model) => ({
          name: lookupModel(model.model_id, models)?.name ?? model.model_id,
          value: model.request_count,
        })),
    [performance, models],
  );

  const successChartData = useMemo(
    () =>
      [...performance]
        .filter((model) => model.request_count > 0)
        .sort((a, b) => b.success_rate - a.success_rate)
        .map((model) => ({
          name: lookupModel(model.model_id, models)?.name ?? model.model_id,
          value: Number((model.success_rate * 100).toFixed(1)),
        })),
    [performance, models],
  );

  const latencyChartData = useMemo(
    () =>
      performance
        .filter((model) => model.average_latency_ms != null)
        .sort((a, b) => (b.average_latency_ms ?? 0) - (a.average_latency_ms ?? 0))
        .map((model) => ({
          name: lookupModel(model.model_id, models)?.name ?? model.model_id,
          value: Number((model.average_latency_ms ?? 0).toFixed(0)),
        })),
    [performance, models],
  );

  const sortedPerformance = useMemo(
    () => [...performance].sort((a, b) => b.request_count - a.request_count),
    [performance],
  );

  const tierUsage = useMemo(
    () => (usage && models.length > 0 ? usageByTier(usage.by_model, models) : []),
    [usage, models],
  );

  const usageGroupOptions = useMemo(
    () =>
      [
        { id: 'model' as const, label: 'By model', available: Boolean(usage?.by_model.length) },
        { id: 'tier' as const, label: 'By tier', available: tierUsage.length > 0 },
        { id: 'user' as const, label: 'By user', available: Boolean(usage?.by_user.length) },
        { id: 'tag' as const, label: 'By tag', available: Boolean(usage?.by_tag.length) },
      ] satisfies { id: UsageGroup; label: string; available: boolean }[],
    [usage, tierUsage],
  );

  const usageRows: UsageBreakdownEntry[] = useMemo(() => {
    if (!usage) return [];
    if (usageGroup === 'model') return usage.by_model;
    if (usageGroup === 'tier') return tierUsage;
    if (usageGroup === 'user') return usage.by_user;
    return usage.by_tag;
  }, [usage, usageGroup, tierUsage]);

  useEffect(() => {
    const selected = usageGroupOptions.find((option) => option.id === usageGroup);
    if (selected && !selected.available && usageGroup !== 'model') {
      setUsageGroup('model');
    }
  }, [usageGroup, usageGroupOptions]);

  const kpiSubtext = `${selectedPeriodLabel} · generation attempts`;

  return (
    <div>
      <PageHeader
        title="Gateway Intelligence"
        description="How the gateway is performing, what it is routing to, and what it is costing — from live routing logs, usage, and model outcomes."
        action={
          <div className="flex flex-col items-stretch gap-3 sm:items-end">
            <div className="flex flex-wrap items-center justify-end gap-2">
              <PeriodSelector value={period} onChange={setPeriod} disabled={performanceLoading && refreshing} />
              <Button variant="secondary" size="sm" onClick={refreshAll} disabled={refreshing || performanceLoading}>
                <RefreshCw className={`h-4 w-4 ${refreshing || performanceLoading ? 'animate-spin' : ''}`} />
                Refresh
              </Button>
            </div>
            <p className="text-xs text-ink-muted">
              Viewing <span className="text-ink-secondary">{selectedPeriodLabel}</span>
              {lastUpdated ? ` · updated ${lastUpdated.toLocaleTimeString()}` : ''}
            </p>
          </div>
        }
      />

      <p className="mb-6 text-xs text-ink-muted">
        Period applies to <span className="text-ink-secondary">/api/performance/models</span> only.
        Routing distribution, cost saved, quality retention, and usage are all-time —
        <span className="text-ink-secondary"> /api/metrics</span> and
        <span className="text-ink-secondary"> /api/usage</span> do not accept a time range.
      </p>

      {metricsError && <ErrorBanner message={metricsError} variant="warning" />}
      {performanceError && <ErrorBanner message={performanceError} variant="warning" />}
      {usageError && <ErrorBanner message={usageError} variant="warning" />}

      {/* KPI row — period-aware where the performance API can support it */}
      <div className={`mb-8 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 ${performanceLoading && !initialLoading ? 'opacity-70' : ''}`}>
        {initialLoading || (performanceLoading && performance.length === 0 && !performanceError) ? (
          Array.from({ length: 6 }).map((_, index) => (
            <Card key={index}>
              <SkeletonBlock className="h-4 w-24" />
              <SkeletonBlock className="mt-3 h-7 w-16" />
            </Card>
          ))
        ) : performanceError ? (
          <>
            <StatCard
              label="Total Requests"
              value={metrics && period === 'all' ? metrics.total_requests.toLocaleString() : '—'}
              subtext={
                metrics && period === 'all'
                  ? 'All time · completed routing log'
                  : 'Unavailable for this period'
              }
            />
            <StatCard label="Success Rate" value="—" subtext="Requires model performance" />
            <StatCard
              label="Avg. Latency"
              value={metrics && period === 'all' ? formatMs(metrics.average_latency_ms) : '—'}
              subtext={metrics && period === 'all' ? 'All time · routing log' : 'Unavailable for this period'}
            />
            <StatCard
              label="Estimated Cost"
              value={metrics && period === 'all' ? formatCost(metrics.total_cost) : '—'}
              subtext={metrics && period === 'all' ? 'All time · routing log' : 'Unavailable for this period'}
            />
            <StatCard
              label="Fallback Rate"
              value={metrics && period === 'all' ? formatPercent(metrics.fallback_rate, 1) : '—'}
              subtext={metrics && period === 'all' ? 'All time · routing log' : 'Unavailable for this period'}
            />
            <StatCard label="Quality-Failure Rate" value="—" subtext="Requires model performance" />
          </>
        ) : (
          <>
            <StatCard
              label="Total Requests"
              value={aggregates.requestCount.toLocaleString()}
              subtext={kpiSubtext}
            />
            <StatCard
              label="Success Rate"
              value={formatPercent(aggregates.successRate, 1)}
              subtext={aggregates.successRate == null ? 'No attempts in this period' : kpiSubtext}
            />
            <StatCard
              label="Avg. Latency"
              value={formatMs(aggregates.averageLatencyMs)}
              subtext={aggregates.averageLatencyMs == null ? 'No successful attempts' : `${kpiSubtext} · successful only`}
            />
            <StatCard
              label="Estimated Cost"
              value={formatCost(aggregates.totalEstimatedCost)}
              subtext={
                aggregates.totalEstimatedCost == null
                  ? 'No priced responses in this period'
                  : `${selectedPeriodLabel} · token usage × registry pricing`
              }
            />
            <StatCard
              label="Fallback Rate"
              value={formatPercent(aggregates.fallbackRate, 1)}
              subtext={aggregates.fallbackRate == null ? 'No attempts in this period' : kpiSubtext}
            />
            <StatCard
              label="Quality-Failure Rate"
              value={formatPercent(aggregates.qualityFailureRate, 1)}
              subtext={
                aggregates.qualityFailureRate == null ? 'No attempts in this period' : kpiSubtext
              }
            />
          </>
        )}
      </div>

      {/* All-time routing log strip — never pretends to be period-filtered */}
      <div className="mb-8">
        <SectionHeading
          title="All-time routing log"
          badge="All time"
          hint="From /api/metrics. These figures are not filtered by the period selector."
        />
        {metricsLoading ? (
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4 xl:grid-cols-7">
            {Array.from({ length: 7 }).map((_, index) => (
              <Card key={index} padding="sm">
                <SkeletonBlock className="h-3 w-16" />
                <SkeletonBlock className="mt-2 h-5 w-12" />
              </Card>
            ))}
          </div>
        ) : metricsError || !metrics ? (
          <EmptyState
            icon={BarChart3}
            title="Routing metrics unavailable"
            description="Completed-request totals, cost saved, and quality retention come from the routing log."
          />
        ) : metrics.total_requests === 0 ? (
          <EmptyState
            icon={Route}
            title="No routing logs yet"
            description="Send a request through Chat or /api/chat to populate all-time routing analytics."
          />
        ) : (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-7">
            <StatCard label="Completed Requests" value={metrics.total_requests.toLocaleString()} />
            <StatCard label="Total Cost" value={formatCost(metrics.total_cost)} />
            <StatCard label="Avg. Cost" value={formatCost(metrics.average_cost)} />
            <StatCard label="Cost Saved vs Strong" value={formatCost(metrics.cost_saved)} />
            <StatCard
              label="Avg. Quality"
              value={formatPercent(metrics.average_quality, 1)}
              subtext={metrics.average_quality == null ? 'No scored responses' : undefined}
            />
            <StatCard
              label="Quality Retention"
              value={formatPercent(metrics.quality_retention, 1)}
              subtext={metrics.quality_retention == null ? 'Needs scored strong-tier traffic' : undefined}
            />
            <StatCard
              label="Strong-Model Share"
              value={formatPercent(metrics.strong_model_usage, 1)}
            />
          </div>
        )}
      </div>

      {/* Routing distribution */}
      <div className="mb-8">
        <SectionHeading
          title="Routing distribution"
          badge="All time"
          hint="Where completed requests were sent — model, tier, and task type."
        />
        {metricsLoading ? (
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2 xl:grid-cols-3">
            {['Requests by model', 'Requests by tier', 'Requests by task type'].map((title) => (
              <ChartCard key={title} title={title} isEmpty={false}>
                <SkeletonBlock className="h-full w-full" />
              </ChartCard>
            ))}
          </div>
        ) : (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2 xl:grid-cols-3">
          <ChartCard
            title="Requests by model"
            isEmpty={modelChartData.length === 0}
            emptyMessage={metricsError ? 'Metrics unavailable.' : 'No routing logs yet.'}
          >
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={modelChartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1f2740" />
                <XAxis dataKey="name" stroke="#707b96" tick={AXIS_TICK} tickFormatter={(value) => truncateLabel(String(value))} />
                <YAxis stroke="#707b96" fontSize={12} allowDecimals={false} />
                <Tooltip
                  contentStyle={CHART_TOOLTIP_STYLE}
                  labelStyle={{ color: '#f4f6fb' }}
                  formatter={(value) => [Number(value).toLocaleString(), 'Requests']}
                />
                <Bar dataKey="value" fill="#6366f1" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>

          <ChartCard
            title="Requests by tier"
            isEmpty={tierChartData.length === 0}
            emptyMessage={metricsError ? 'Metrics unavailable.' : 'No routing logs yet.'}
          >
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={tierChartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1f2740" />
                <XAxis dataKey="name" stroke="#707b96" tick={AXIS_TICK} />
                <YAxis stroke="#707b96" fontSize={12} allowDecimals={false} />
                <Tooltip
                  contentStyle={CHART_TOOLTIP_STYLE}
                  labelStyle={{ color: '#f4f6fb' }}
                  formatter={(value) => [Number(value).toLocaleString(), 'Requests']}
                />
                <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                  {tierChartData.map((entry) => (
                    <Cell key={entry.name} fill={TIER_BAR_COLORS[entry.name] ?? '#6366f1'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>

          <ChartCard
            title="Requests by task type"
            isEmpty={taskChartData.length === 0}
            emptyMessage={metricsError ? 'Metrics unavailable.' : 'No task labels in the routing log yet.'}
          >
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={taskChartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1f2740" />
                <XAxis dataKey="name" stroke="#707b96" tick={AXIS_TICK} tickFormatter={(value) => truncateLabel(String(value))} />
                <YAxis stroke="#707b96" fontSize={12} allowDecimals={false} />
                <Tooltip
                  contentStyle={CHART_TOOLTIP_STYLE}
                  labelStyle={{ color: '#f4f6fb' }}
                  formatter={(value) => [Number(value).toLocaleString(), 'Requests']}
                />
                <Bar dataKey="value" fill="#38bdf8" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>
        </div>
        )}
      </div>

      {/* Performance visualization */}
      <div className="mb-8">
        <SectionHeading
          title="Model performance"
          badge={selectedPeriodLabel}
          hint="Generation attempts, including fallbacks and escalations."
        />
        {performanceError ? (
          <EmptyState
            icon={Activity}
            title="Performance data unavailable"
            description="Charts and the comparison table need /api/performance/models."
          />
        ) : (
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
            <ChartCard
              title="Attempts by model"
              isEmpty={!performanceLoading && volumeChartData.length === 0}
              emptyMessage={`No generation attempts in ${selectedPeriodLabel.toLowerCase()}.`}
            >
              {performanceLoading && volumeChartData.length === 0 ? (
                <SkeletonBlock className="h-full w-full" />
              ) : (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={volumeChartData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1f2740" />
                    <XAxis dataKey="name" stroke="#707b96" tick={AXIS_TICK} tickFormatter={(value) => truncateLabel(String(value))} />
                    <YAxis stroke="#707b96" fontSize={12} allowDecimals={false} />
                    <Tooltip
                      contentStyle={CHART_TOOLTIP_STYLE}
                      labelStyle={{ color: '#f4f6fb' }}
                      formatter={(value) => [Number(value).toLocaleString(), 'Attempts']}
                    />
                    <Bar dataKey="value" fill="#6366f1" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </ChartCard>

            <ChartCard
              title="Success rate by model"
              isEmpty={!performanceLoading && successChartData.length === 0}
              emptyMessage={`No generation attempts in ${selectedPeriodLabel.toLowerCase()}.`}
            >
              {performanceLoading && successChartData.length === 0 ? (
                <SkeletonBlock className="h-full w-full" />
              ) : (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={successChartData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1f2740" />
                    <XAxis dataKey="name" stroke="#707b96" tick={AXIS_TICK} tickFormatter={(value) => truncateLabel(String(value))} />
                    <YAxis stroke="#707b96" fontSize={12} domain={[0, 100]} tickFormatter={(value) => `${value}%`} />
                    <Tooltip
                      contentStyle={CHART_TOOLTIP_STYLE}
                      labelStyle={{ color: '#f4f6fb' }}
                      formatter={(value) => [`${Number(value).toFixed(1)}%`, 'Success']}
                    />
                    <Bar dataKey="value" fill="#34d399" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </ChartCard>

            <ChartCard
              title="Avg. latency by model"
              isEmpty={!performanceLoading && latencyChartData.length === 0}
              emptyMessage="No successful attempts with latency in this period."
            >
              {performanceLoading && latencyChartData.length === 0 ? (
                <SkeletonBlock className="h-full w-full" />
              ) : (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={latencyChartData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1f2740" />
                    <XAxis dataKey="name" stroke="#707b96" tick={AXIS_TICK} tickFormatter={(value) => truncateLabel(String(value))} />
                    <YAxis stroke="#707b96" fontSize={12} tickFormatter={(value) => `${value}ms`} />
                    <Tooltip
                      contentStyle={CHART_TOOLTIP_STYLE}
                      labelStyle={{ color: '#f4f6fb' }}
                      formatter={(value) => [formatMs(Number(value)), 'Avg. latency']}
                    />
                    <Bar dataKey="value" fill="#fbbf24" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </ChartCard>
          </div>
        )}
      </div>

      {/* Model comparison table */}
      <div className="mb-8">
        <SectionHeading
          title="Model comparison"
          badge={selectedPeriodLabel}
          hint="Same tier labels as the Models registry. Latency and cost average successful responses only."
        />
        {performanceLoading && sortedPerformance.length === 0 ? (
          <SkeletonRows rows={4} cols={9} />
        ) : performanceError ? (
          <EmptyState
            icon={AlertTriangle}
            title="Comparison unavailable"
            description="The model performance API did not respond."
          />
        ) : sortedPerformance.length === 0 ? (
          <EmptyState
            icon={Clock}
            title="No attempts in this period"
            description={`Nothing was recorded for ${selectedPeriodLabel.toLowerCase()}. Try All time or send traffic through the gateway.`}
          />
        ) : (
          <TableContainer>
            <Table className="min-w-[1100px]">
              <THead>
                <Tr className="hover:bg-transparent">
                  <Th>Model</Th>
                  <Th>Tier</Th>
                  <Th>Requests</Th>
                  <Th>Success</Th>
                  <Th>Quality-failure</Th>
                  <Th>Fallback</Th>
                  <Th>Avg. latency</Th>
                  <Th>Avg. cost</Th>
                  <Th>Avg. quality</Th>
                </Tr>
              </THead>
              <TBody>
                {sortedPerformance.map((row) => {
                  const registered = lookupModel(row.model_id, models);
                  const tier = registered?.tier;
                  return (
                    <Tr key={row.model_id}>
                      <Td>
                        <div className="font-medium text-ink-primary">{registered?.name ?? row.model_id}</div>
                        <div className="font-mono text-xs text-ink-muted">{row.model_id}</div>
                        <div className="text-xs capitalize text-ink-muted">{row.provider}</div>
                      </Td>
                      <Td>
                        {tier ? (
                          <Badge variant={tier}>{tier}</Badge>
                        ) : (
                          <span className="text-ink-muted">—</span>
                        )}
                      </Td>
                      <Td className="text-ink-secondary">{row.request_count.toLocaleString()}</Td>
                      <Td className="text-ink-secondary">{formatPercent(row.success_rate, 1)}</Td>
                      <Td className="text-ink-secondary">{formatPercent(row.quality_failure_rate, 1)}</Td>
                      <Td className="text-ink-secondary">{formatPercent(row.fallback_rate, 1)}</Td>
                      <Td className="whitespace-nowrap text-ink-secondary">{formatMs(row.average_latency_ms)}</Td>
                      <Td className="whitespace-nowrap text-ink-secondary">{formatCost(row.average_estimated_cost)}</Td>
                      <Td className="text-ink-secondary">{formatPercent(row.average_quality_score, 1)}</Td>
                    </Tr>
                  );
                })}
              </TBody>
            </Table>
          </TableContainer>
        )}
      </div>

      {/* Usage breakdown */}
      <div className="mb-4">
        <SectionHeading
          title="Usage breakdown"
          badge="All time"
          hint="From /api/usage. Filterable on the API by user, session, model, and tag — this view is unfiltered. No since/until."
        />
        {usageLoading ? (
          <SkeletonRows rows={4} cols={6} />
        ) : usageError || !usage ? (
          <EmptyState
            icon={Wallet}
            title="Usage unavailable"
            description="Per-model and per-user spend comes from /api/usage."
          />
        ) : usage.total_requests === 0 ? (
          <EmptyState
            icon={Wallet}
            title="No usage recorded"
            description="Completed requests are counted here after they are written to the routing log."
          />
        ) : (
          <>
            <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
              <StatCard label="Completed Requests" value={usage.total_requests.toLocaleString()} />
              <StatCard
                label="Estimated Cost"
                value={formatCost(usage.total_estimated_cost)}
                subtext="Token usage × registry pricing"
              />
              <StatCard label="Avg. Latency" value={formatMs(usage.average_latency_ms)} />
              <StatCard
                label="Fallback Requests"
                value={usage.fallback_requests.toLocaleString()}
                subtext={`${formatPercent(usage.total_requests > 0 ? usage.fallback_requests / usage.total_requests : null, 1)} of completed requests`}
              />
            </div>

            <div className="mb-3 inline-flex flex-wrap rounded-lg border border-line bg-surface-1 p-0.5" role="tablist" aria-label="Usage grouping">
              {usageGroupOptions.map((option) => {
                const selected = usageGroup === option.id;
                return (
                  <button
                    key={option.id}
                    type="button"
                    role="tab"
                    aria-selected={selected}
                    disabled={!option.available}
                    onClick={() => setUsageGroup(option.id)}
                    className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${
                      selected ? 'bg-surface-3 text-ink-primary' : 'text-ink-muted hover:text-ink-secondary'
                    }`}
                  >
                    {option.label}
                  </button>
                );
              })}
            </div>

            {usageGroup === 'tier' && models.length === 0 ? (
              <EmptyState
                icon={Route}
                title="Tier grouping needs the model registry"
                description="Tier is not returned by /api/usage; it is joined from registered model IDs."
              />
            ) : usageRows.length === 0 ? (
              <EmptyState
                icon={Wallet}
                title={`No ${usageGroup} breakdown`}
                description={
                  usageGroup === 'tag'
                    ? 'Requests in this log do not carry tags.'
                    : `No ${usageGroup} keys in the usage response.`
                }
              />
            ) : (
              <TableContainer>
                <Table>
                  <THead>
                    <Tr className="hover:bg-transparent">
                      <Th>{usageGroup === 'tag' ? 'Tag' : usageGroup === 'user' ? 'User' : usageGroup === 'tier' ? 'Tier' : 'Model'}</Th>
                      <Th>Requests</Th>
                      <Th>Successful</Th>
                      <Th>Fallback</Th>
                      <Th>Avg. latency</Th>
                      <Th>Est. cost</Th>
                    </Tr>
                  </THead>
                  <TBody>
                    {usageRows.map((entry) => (
                      <Tr key={`${usageGroup}-${entry.key}`}>
                        <Td>
                          {usageGroup === 'tier' && isModelTier(entry.key) ? (
                            <Badge variant={entry.key}>{entry.key}</Badge>
                          ) : usageGroup === 'tier' && entry.key === 'unknown' ? (
                            <span className="text-ink-muted">Unregistered model</span>
                          ) : usageGroup === 'model' ? (
                            <>
                              <div className="font-medium text-ink-primary">
                                {lookupModel(entry.key, models)?.name ?? entry.key}
                              </div>
                              <div className="font-mono text-xs text-ink-muted">{entry.key}</div>
                            </>
                          ) : (
                            <span className="font-medium text-ink-primary">{entry.key}</span>
                          )}
                        </Td>
                        <Td className="text-ink-secondary">{entry.total_requests.toLocaleString()}</Td>
                        <Td className="text-ink-secondary">{entry.successful_requests.toLocaleString()}</Td>
                        <Td className="text-ink-secondary">{entry.fallback_requests.toLocaleString()}</Td>
                        <Td className="whitespace-nowrap text-ink-secondary">{formatMs(entry.average_latency_ms)}</Td>
                        <Td className="whitespace-nowrap text-ink-secondary">{formatCost(entry.total_estimated_cost)}</Td>
                      </Tr>
                    ))}
                  </TBody>
                </Table>
              </TableContainer>
            )}
          </>
        )}
      </div>
    </div>
  );
}
