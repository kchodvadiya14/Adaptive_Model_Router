import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowRight,
  BarChart3,
  Bot,
  Database,
  FlaskConical,
  HeartPulse,
  MessageSquare,
  RefreshCw,
} from 'lucide-react';
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Badge } from '../components/Badge';
import { Button } from '../components/Button';
import { Card } from '../components/Card';
import { ChartCard } from '../components/ChartCard';
import { EmptyState } from '../components/EmptyState';
import { ErrorBanner } from '../components/ErrorBanner';
import { PageHeader } from '../components/PageHeader';
import { StatCard } from '../components/StatCard';
import { TableContainer, Table, THead, TBody, Tr, Th, Td } from '../components/Table';
import {
  fetchHealth,
  fetchMetrics,
  fetchModelHealth,
  fetchModelPerformance,
  fetchRouterStatus,
  fetchUsage,
} from '../services/api';
import type {
  HealthResponse,
  MetricsSummary,
  ModelHealthStatus,
  ModelPerformance,
  RouterStatusResponse,
  UsageBreakdownEntry,
} from '../types';

const quickLinks = [
  { to: '/chat', label: 'Chat', icon: MessageSquare },
  { to: '/models', label: 'Models', icon: Bot },
  { to: '/analytics', label: 'Analytics', icon: BarChart3 },
  { to: '/benchmark', label: 'Benchmark', icon: FlaskConical },
  { to: '/dataset', label: 'Dataset', icon: Database },
];

function formatMs(value: number | null | undefined): string {
  if (value == null) return '—';
  return `${value.toFixed(0)} ms`;
}

function formatCost(value: number | null | undefined): string {
  if (value == null) return '—';
  return `$${value.toFixed(6)}`;
}

function formatPct(value: number | null | undefined): string {
  if (value == null) return '—';
  return `${(value * 100).toFixed(1)}%`;
}

function formatTimestamp(value: string | null | undefined): string {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString();
}

function SkeletonBlock({ className = '' }: { className?: string }) {
  return <div className={`animate-pulse rounded-lg bg-surface-3 ${className}`} />;
}

function SkeletonRows({ rows = 3, cols = 5 }: { rows?: number; cols?: number }) {
  return (
    <TableContainer>
      <Table>
        <TBody>
          {Array.from({ length: rows }).map((_, rowIndex) => (
            <Tr key={rowIndex}>
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

export function OverviewPage() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [routerStatus, setRouterStatus] = useState<RouterStatusResponse | null>(null);
  const [metrics, setMetrics] = useState<MetricsSummary | null>(null);
  const [modelHealth, setModelHealth] = useState<ModelHealthStatus[]>([]);
  const [modelPerformance, setModelPerformance] = useState<ModelPerformance[]>([]);
  const [usageByModel, setUsageByModel] = useState<UsageBreakdownEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const loadOverview = useCallback(async (isInitial = false) => {
    if (isInitial) setLoading(true);
    else setRefreshing(true);

    try {
      const [healthData, statusData, metricsData, healthList, performance, usage] = await Promise.all([
        fetchHealth().catch(() => null),
        fetchRouterStatus().catch(() => null),
        fetchMetrics().catch(() => null),
        fetchModelHealth().catch(() => []),
        fetchModelPerformance().catch(() => null),
        fetchUsage().catch(() => null),
      ]);
      setHealth(healthData);
      setRouterStatus(statusData);
      setMetrics(metricsData);
      setModelHealth(healthList);
      setModelPerformance(performance?.models ?? []);
      setUsageByModel(usage?.by_model ?? []);
      setError(null);
      setLastUpdated(new Date());
    } catch {
      setError('Failed to load gateway overview. Ensure the backend is running.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadOverview(true);
  }, [loadOverview]);

  const isOnline = health?.status === 'ok';

  const aggregateSuccessRate = modelPerformance.length
    ? modelPerformance.reduce((sum, m) => sum + m.success_count, 0) /
      Math.max(1, modelPerformance.reduce((sum, m) => sum + m.request_count, 0))
    : null;

  const tierChartData = metrics
    ? Object.entries(metrics.requests_by_tier).map(([tier, count]) => ({ tier, count }))
    : [];

  return (
    <div>
      <PageHeader
        title="Adaptive AI Gateway"
        description="Real-time visibility into routing decisions, model health, latency, cost, and fallback behavior across the gateway."
        action={
          <div className="flex flex-col items-end gap-2">
            <div className="flex items-center gap-2">
              <Badge variant={isOnline ? 'success' : 'error'}>
                <span
                  className={`mr-1.5 h-1.5 w-1.5 rounded-full ${isOnline ? 'bg-success-400' : 'bg-danger-400'}`}
                />
                {isOnline ? 'Gateway Online' : 'Gateway Offline'}
              </Badge>
              <Button variant="secondary" size="sm" onClick={() => loadOverview(false)} loading={refreshing}>
                <RefreshCw className="h-4 w-4" />
                Refresh
              </Button>
            </div>
            <p className="text-xs text-ink-muted">
              {lastUpdated ? `Last updated ${lastUpdated.toLocaleTimeString()}` : 'Not yet updated'}
            </p>
          </div>
        }
      />

      {error && <ErrorBanner message={error} variant="error" />}

      {routerStatus && (
        <p className="mb-6 text-xs text-ink-muted">
          Router: <span className="text-ink-secondary">{routerStatus.router_type}</span> · Quality floor{' '}
          <span className="text-ink-secondary">{(routerStatus.quality_floor * 100).toFixed(0)}%</span> · Fallback{' '}
          <span className="text-ink-secondary">{routerStatus.fallback_enabled ? 'on' : 'off'}</span> ·{' '}
          <span className="text-ink-secondary">
            {routerStatus.enabled_models}/{routerStatus.total_models}
          </span>{' '}
          models enabled
        </p>
      )}

      {/* KPI row */}
      <div className="mb-8 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
        {loading ? (
          Array.from({ length: 6 }).map((_, i) => (
            <Card key={i}>
              <SkeletonBlock className="h-4 w-20" />
              <SkeletonBlock className="mt-3 h-7 w-16" />
            </Card>
          ))
        ) : (
          <>
            <StatCard label="Total Requests" value={metrics?.total_requests ?? 0} />
            <StatCard
              label="Success Rate"
              value={formatPct(aggregateSuccessRate)}
              subtext={modelPerformance.length ? undefined : 'No attempts recorded yet'}
            />
            <StatCard label="Avg. Latency" value={metrics ? formatMs(metrics.average_latency_ms) : '—'} />
            <StatCard label="Estimated Cost" value={metrics ? formatCost(metrics.total_cost) : '—'} />
            <StatCard
              label="Fallback Rate"
              value={metrics ? formatPct(metrics.fallback_rate) : '—'}
            />
            <StatCard label="Cost Saved" value={metrics ? formatCost(metrics.cost_saved) : '—'} />
          </>
        )}
      </div>

      {/* Model health */}
      <div className="mb-8">
        <div className="mb-3 flex items-center gap-2">
          <HeartPulse className="h-4 w-4 text-ink-secondary" />
          <h3 className="text-sm font-medium text-ink-primary">Model Health</h3>
        </div>
        {loading ? (
          <SkeletonRows rows={3} cols={6} />
        ) : modelHealth.length === 0 ? (
          <EmptyState icon={HeartPulse} title="No models registered" description="Register a model to see its live circuit-breaker health here." />
        ) : (
          <TableContainer>
            <Table>
              <THead>
                <Tr>
                  <Th>Model</Th>
                  <Th>Provider</Th>
                  <Th>State</Th>
                  <Th>Consecutive Failures</Th>
                  <Th>Cooldown Remaining</Th>
                  <Th>Last Success</Th>
                  <Th>Last Failure</Th>
                </Tr>
              </THead>
              <TBody>
                {modelHealth.map((m) => (
                  <Tr key={m.model_id}>
                    <Td className="font-medium text-ink-primary">{m.model_id}</Td>
                    <Td className="capitalize text-ink-secondary">{m.provider}</Td>
                    <Td>
                      <Badge variant={m.state}>{m.state.replace('_', ' ')}</Badge>
                    </Td>
                    <Td className="text-ink-secondary">{m.consecutive_failures}</Td>
                    <Td className="text-ink-secondary">
                      {m.cooldown_remaining_seconds != null ? `${m.cooldown_remaining_seconds.toFixed(0)}s` : '—'}
                    </Td>
                    <Td className="text-ink-secondary">{formatTimestamp(m.last_success)}</Td>
                    <Td className="text-ink-secondary">{formatTimestamp(m.last_failure)}</Td>
                  </Tr>
                ))}
              </TBody>
            </Table>
          </TableContainer>
        )}
      </div>

      {/* Routing activity */}
      <div className="mb-8">
        <h3 className="mb-3 text-sm font-medium text-ink-primary">Routing Activity by Model</h3>
        {loading ? (
          <SkeletonRows rows={3} cols={5} />
        ) : usageByModel.length === 0 ? (
          <EmptyState
            icon={BarChart3}
            title="No routing activity yet"
            description="Send a request through /chat or /route to see per-model activity here."
          />
        ) : (
          <TableContainer>
            <Table>
              <THead>
                <Tr>
                  <Th>Model</Th>
                  <Th>Requests</Th>
                  <Th>Fallback Requests</Th>
                  <Th>Avg. Latency</Th>
                  <Th>Est. Cost</Th>
                </Tr>
              </THead>
              <TBody>
                {usageByModel.map((entry) => (
                  <Tr key={entry.key}>
                    <Td className="font-medium text-ink-primary">{entry.key}</Td>
                    <Td className="text-ink-secondary">{entry.total_requests}</Td>
                    <Td className="text-ink-secondary">{entry.fallback_requests}</Td>
                    <Td className="text-ink-secondary">{formatMs(entry.average_latency_ms)}</Td>
                    <Td className="text-ink-secondary">{formatCost(entry.total_estimated_cost)}</Td>
                  </Tr>
                ))}
              </TBody>
            </Table>
          </TableContainer>
        )}
      </div>

      {/* Model performance */}
      <div className="mb-8">
        <h3 className="mb-3 text-sm font-medium text-ink-primary">Model Performance</h3>
        {loading ? (
          <SkeletonRows rows={3} cols={6} />
        ) : modelPerformance.length === 0 ? (
          <EmptyState
            icon={Bot}
            title="No performance data yet"
            description="Performance metrics appear here once models have handled requests."
          />
        ) : (
          <TableContainer>
            <Table>
              <THead>
                <Tr>
                  <Th>Model</Th>
                  <Th>Provider</Th>
                  <Th>Requests</Th>
                  <Th>Success Rate</Th>
                  <Th>Avg. Quality</Th>
                  <Th>Avg. Latency</Th>
                  <Th>Fallback Rate</Th>
                </Tr>
              </THead>
              <TBody>
                {modelPerformance.map((m) => (
                  <Tr key={m.model_id}>
                    <Td className="font-medium text-ink-primary">{m.model_id}</Td>
                    <Td className="capitalize text-ink-secondary">{m.provider}</Td>
                    <Td className="text-ink-secondary">{m.request_count}</Td>
                    <Td className="text-ink-secondary">{formatPct(m.success_rate)}</Td>
                    <Td className="text-ink-secondary">{formatPct(m.average_quality_score)}</Td>
                    <Td className="text-ink-secondary">{formatMs(m.average_latency_ms)}</Td>
                    <Td className="text-ink-secondary">{formatPct(m.fallback_rate)}</Td>
                  </Tr>
                ))}
              </TBody>
            </Table>
          </TableContainer>
        )}
      </div>

      {/* Tier distribution chart */}
      <div className="mb-8">
        <ChartCard title="Requests by Tier" isEmpty={tierChartData.length === 0} emptyMessage="No routing logs yet.">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={tierChartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1f2740" />
              <XAxis dataKey="tier" stroke="#707b96" fontSize={12} />
              <YAxis stroke="#707b96" fontSize={12} allowDecimals={false} />
              <Tooltip
                contentStyle={{ background: '#121a2c', border: '1px solid #1f2740', borderRadius: 8 }}
                labelStyle={{ color: '#f4f6fb' }}
              />
              <Bar dataKey="count" fill="#6366f1" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      {/* Quick navigation */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        {quickLinks.map(({ to, label, icon: Icon }) => (
          <Link key={to} to={to}>
            <Card padding="sm" className="group flex items-center justify-between transition-colors hover:border-brand-500/40 hover:bg-surface-3/60">
              <div className="flex items-center gap-2.5">
                <Icon className="h-4 w-4 text-brand-300" />
                <span className="text-sm font-medium text-ink-primary">{label}</span>
              </div>
              <ArrowRight className="h-3.5 w-3.5 text-ink-disabled transition-transform group-hover:translate-x-0.5 group-hover:text-brand-300" />
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}
