import { useCallback, useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { ChartCard } from '../components/ChartCard';
import { ErrorBanner } from '../components/ErrorBanner';
import { PageHeader } from '../components/PageHeader';
import { StatCard } from '../components/StatCard';
import { fetchMetrics } from '../services/api';
import type { MetricsSummary } from '../types';

export function AnalyticsPage() {
  const [metrics, setMetrics] = useState<MetricsSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadMetrics = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchMetrics();
      setMetrics(data);
      setError(data.total_requests === 0 ? 'No routing logs yet. Send a chat request first.' : null);
    } catch {
      setError('Failed to load metrics. Ensure the backend is running.');
      setMetrics(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadMetrics();
  }, [loadMetrics]);

  const modelChartData = metrics
    ? Object.entries(metrics.requests_by_model).map(([name, value]) => ({ name, value }))
    : [];
  const taskChartData = metrics
    ? Object.entries(metrics.requests_by_task).map(([name, value]) => ({ name, value }))
    : [];
  const tierChartData = metrics
    ? Object.entries(metrics.requests_by_tier).map(([name, value]) => ({ name, value }))
    : [];

  return (
    <div>
      <PageHeader
        title="Routing Analytics"
        description="Live cost, quality, latency, and model utilization from logged routing decisions."
        action={
          <button
            onClick={loadMetrics}
            disabled={loading}
            className="flex items-center gap-2 rounded-lg border border-slate-700 px-4 py-2 text-sm text-slate-300 hover:bg-slate-800 disabled:opacity-50"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        }
      />

      {error && <ErrorBanner message={error} variant="warning" />}

      <div className="mb-6 grid grid-cols-1 gap-4 md:grid-cols-3 xl:grid-cols-4">
        <StatCard label="Total Requests" value={metrics?.total_requests ?? '—'} />
        <StatCard label="Total Cost" value={metrics ? `$${metrics.total_cost.toFixed(6)}` : '—'} />
        <StatCard label="Average Cost" value={metrics ? `$${metrics.average_cost.toFixed(6)}` : '—'} />
        <StatCard label="Cost Saved" value={metrics ? `$${metrics.cost_saved.toFixed(6)}` : '—'} />
        <StatCard
          label="Avg Quality"
          value={metrics?.average_quality != null ? `${(metrics.average_quality * 100).toFixed(1)}%` : '—'}
        />
        <StatCard
          label="Quality Retention"
          value={metrics?.quality_retention != null ? `${(metrics.quality_retention * 100).toFixed(1)}%` : '—'}
        />
        <StatCard
          label="Avg Latency"
          value={metrics ? `${metrics.average_latency_ms.toFixed(0)} ms` : '—'}
        />
        <StatCard
          label="Fallback Rate"
          value={metrics ? `${(metrics.fallback_rate * 100).toFixed(1)}%` : '—'}
        />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2 xl:grid-cols-3">
        <ChartCard title="Requests by Model" isEmpty={modelChartData.length === 0}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={modelChartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="name" tick={{ fill: '#94a3b8', fontSize: 11 }} />
              <YAxis tick={{ fill: '#94a3b8', fontSize: 12 }} />
              <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #334155' }} />
              <Bar dataKey="value" fill="#6366f1" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Routing Decisions by Task" isEmpty={taskChartData.length === 0}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={taskChartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="name" tick={{ fill: '#94a3b8', fontSize: 11 }} />
              <YAxis tick={{ fill: '#94a3b8', fontSize: 12 }} />
              <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #334155' }} />
              <Bar dataKey="value" fill="#22c55e" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Requests by Tier" isEmpty={tierChartData.length === 0}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={tierChartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="name" tick={{ fill: '#94a3b8', fontSize: 12 }} />
              <YAxis tick={{ fill: '#94a3b8', fontSize: 12 }} />
              <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #334155' }} />
              <Bar dataKey="value" fill="#f59e0b" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>
    </div>
  );
}
