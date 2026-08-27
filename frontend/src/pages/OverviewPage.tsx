import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowRight,
  BarChart3,
  Bot,
  Database,
  FlaskConical,
  MessageSquare,
  Microscope,
} from 'lucide-react';
import { ErrorBanner } from '../components/ErrorBanner';
import { PageHeader } from '../components/PageHeader';
import { StatCard } from '../components/StatCard';
import {
  fetchBenchmarks,
  fetchDatasets,
  fetchHealth,
  fetchMetrics,
  fetchRouterStatus,
  fetchTrainedModels,
} from '../services/api';
import type { BenchmarkReport, HealthResponse, MetricsSummary, RouterStatusResponse } from '../types';

const quickLinks = [
  { to: '/chat', label: 'Chat', icon: MessageSquare, description: 'Send prompts with adaptive routing' },
  { to: '/analytics', label: 'Analytics', icon: BarChart3, description: 'Cost, quality, and utilization' },
  { to: '/models', label: 'Models', icon: Bot, description: 'Manage provider registry' },
  { to: '/benchmark', label: 'Benchmark', icon: FlaskConical, description: 'Compare routing strategies' },
  { to: '/dataset', label: 'Dataset', icon: Database, description: 'Preference data pipeline' },
  { to: '/experiments', label: 'Experiments', icon: Microscope, description: 'Final evaluation suite' },
];

export function OverviewPage() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [routerStatus, setRouterStatus] = useState<RouterStatusResponse | null>(null);
  const [metrics, setMetrics] = useState<MetricsSummary | null>(null);
  const [datasetCount, setDatasetCount] = useState(0);
  const [trainedCount, setTrainedCount] = useState(0);
  const [recentBenchmarks, setRecentBenchmarks] = useState<BenchmarkReport[]>([]);
  const [error, setError] = useState<string | null>(null);

  const loadOverview = useCallback(async () => {
    try {
      const [healthData, statusData, metricsData, datasets, trained, benchmarks] = await Promise.all([
        fetchHealth(),
        fetchRouterStatus(),
        fetchMetrics().catch(() => null),
        fetchDatasets().catch(() => []),
        fetchTrainedModels().catch(() => []),
        fetchBenchmarks().catch(() => []),
      ]);
      setHealth(healthData);
      setRouterStatus(statusData);
      setMetrics(metricsData);
      setDatasetCount(datasets.length);
      setTrainedCount(trained.length);
      setRecentBenchmarks(benchmarks.slice(0, 3));
      setError(null);
    } catch {
      setError('Failed to load dashboard overview. Ensure the backend is running.');
    }
  }, []);

  useEffect(() => {
    loadOverview();
  }, [loadOverview]);

  return (
    <div>
      <PageHeader
        title="Dashboard Overview"
        description="Monitor routing performance, manage models, and run experiments from one place."
        action={
          <button
            onClick={loadOverview}
            className="rounded-lg border border-slate-700 px-4 py-2 text-sm text-slate-300 hover:bg-slate-800"
          >
            Refresh
          </button>
        }
      />

      {error && <ErrorBanner message={error} variant="warning" />}

      <div className="mb-8 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="System"
          value={health?.status ?? 'offline'}
          subtext={health ? `${health.app_name} v${health.version}` : 'Backend unavailable'}
        />
        <StatCard
          label="Router"
          value={routerStatus?.router_type ?? '—'}
          subtext={
            routerStatus
              ? `${routerStatus.enabled_models}/${routerStatus.total_models} models enabled`
              : 'Loading...'
          }
        />
        <StatCard
          label="Total Requests"
          value={metrics?.total_requests ?? 0}
          subtext={metrics ? `$${metrics.total_cost.toFixed(6)} total cost` : 'No routing logs yet'}
        />
        <StatCard
          label="Cost Saved"
          value={metrics ? `$${metrics.cost_saved.toFixed(6)}` : '—'}
          subtext={
            metrics?.fallback_rate != null
              ? `${(metrics.fallback_rate * 100).toFixed(1)}% fallback rate`
              : undefined
          }
        />
      </div>

      <div className="mb-8 grid grid-cols-1 gap-4 md:grid-cols-3">
        <StatCard label="Datasets" value={datasetCount} subtext="Preference datasets for training" />
        <StatCard label="Trained Routers" value={trainedCount} subtext="ML artifacts in models/" />
        <StatCard
          label="Quality Floor"
          value={routerStatus ? `${(routerStatus.quality_floor * 100).toFixed(0)}%` : '—'}
          subtext={
            routerStatus
              ? `Fallback ${routerStatus.fallback_enabled ? 'on' : 'off'} · cost ${routerStatus.cost_priority}`
              : undefined
          }
        />
      </div>

      <div className="mb-8 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        {quickLinks.map(({ to, label, icon: Icon, description }) => (
          <Link
            key={to}
            to={to}
            className="group rounded-xl border border-slate-800 bg-slate-900/60 p-5 transition-colors hover:border-brand-500/40 hover:bg-slate-900"
          >
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-brand-600/20">
                  <Icon className="h-5 w-5 text-brand-300" />
                </div>
                <div>
                  <h3 className="text-sm font-medium text-white">{label}</h3>
                  <p className="mt-1 text-xs text-slate-400">{description}</p>
                </div>
              </div>
              <ArrowRight className="h-4 w-4 text-slate-600 transition-transform group-hover:translate-x-0.5 group-hover:text-brand-300" />
            </div>
          </Link>
        ))}
      </div>

      {recentBenchmarks.length > 0 && (
        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-5">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-medium text-white">Recent Benchmarks</h3>
            <Link to="/benchmark" className="text-xs text-brand-300 hover:text-brand-200">
              View all
            </Link>
          </div>
          <ul className="mt-3 space-y-2 text-sm text-slate-400">
            {recentBenchmarks.map((item) => (
              <li key={item.id}>
                {new Date(item.created_at).toLocaleString()} · floor {(item.quality_floor * 100).toFixed(0)}% ·{' '}
                {item.strategies.length} strategies
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
