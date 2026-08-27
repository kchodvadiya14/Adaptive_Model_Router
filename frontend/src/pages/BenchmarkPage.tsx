import { useEffect, useState } from 'react';
import { Loader2, Play } from 'lucide-react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { ChartCard } from '../components/ChartCard';
import { ErrorBanner } from '../components/ErrorBanner';
import { JobProgressBar } from '../components/JobProgressBar';
import { PageHeader } from '../components/PageHeader';
import { StatCard } from '../components/StatCard';
import {
  fetchBenchmarkReport,
  fetchBenchmarkStatus,
  fetchBenchmarks,
  startBenchmark,
} from '../services/api';
import type { BenchmarkReport, BenchmarkStrategy } from '../types';

const strategyLabels: Record<string, string> = {
  always_strong: 'Always Strong',
  always_cheap: 'Always Cheap',
  adaptive_router: 'Adaptive Router',
};

const allStrategies: BenchmarkStrategy[] = ['always_strong', 'always_cheap', 'adaptive_router'];

export function BenchmarkPage() {
  const [datasetPath, setDatasetPath] = useState('data/benchmarks/sample_prompts.json');
  const [qualityFloor, setQualityFloor] = useState(0.9);
  const [maxPrompts, setMaxPrompts] = useState(8);
  const [strategies, setStrategies] = useState<BenchmarkStrategy[]>(allStrategies);
  const [jobId, setJobId] = useState<string | null>(null);
  const [jobProgress, setJobProgress] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<BenchmarkReport | null>(null);
  const [history, setHistory] = useState<BenchmarkReport[]>([]);

  useEffect(() => {
    fetchBenchmarks().then(setHistory).catch(() => undefined);
  }, [report]);

  useEffect(() => {
    if (!jobId) return;
    const interval = setInterval(async () => {
      try {
        const status = await fetchBenchmarkStatus(jobId);
        setJobProgress(status.progress);
        if (status.status === 'completed' && status.report) {
          setReport(status.report);
          setLoading(false);
          setJobId(null);
        } else if (status.status === 'failed') {
          setError(status.error ?? 'Benchmark failed');
          setLoading(false);
          setJobId(null);
        }
      } catch {
        setError('Failed to poll benchmark status');
        setLoading(false);
        setJobId(null);
      }
    }, 1500);
    return () => clearInterval(interval);
  }, [jobId]);

  const toggleStrategy = (strategy: BenchmarkStrategy) => {
    setStrategies((prev) =>
      prev.includes(strategy) ? prev.filter((s) => s !== strategy) : [...prev, strategy],
    );
  };

  const handleRun = async () => {
    if (strategies.length === 0) {
      setError('Select at least one strategy.');
      return;
    }
    setLoading(true);
    setError(null);
    setReport(null);
    setJobProgress(0);
    try {
      const job = await startBenchmark({
        dataset_path: datasetPath,
        quality_floor: qualityFloor,
        max_prompts: maxPrompts,
        strategies,
      });
      setJobId(job.job_id);
    } catch {
      setError('Failed to start benchmark. Ensure backend is running.');
      setLoading(false);
    }
  };

  const loadReport = async (reportId: string) => {
    try {
      setReport(await fetchBenchmarkReport(reportId));
    } catch {
      setError('Failed to load benchmark report.');
    }
  };

  const chartData =
    report?.strategies.map((item) => ({
      name: strategyLabels[item.strategy] ?? item.strategy,
      quality: Number((item.metrics.average_quality * 100).toFixed(1)),
      costReduction: Number((item.metrics.cost_reduction * 100).toFixed(1)),
      qualityRetention: Number((item.metrics.quality_retention * 100).toFixed(1)),
      routingAccuracy: Number((item.metrics.routing_accuracy * 100).toFixed(1)),
    })) ?? [];

  return (
    <div>
      <PageHeader
        title="Benchmark"
        description="Compare Always Strong, Always Cheap, and Adaptive Router using controlled experiments."
      />

      <div className="mb-6 space-y-4 rounded-xl border border-slate-800 bg-slate-900/60 p-5">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <label className="text-sm text-slate-400 md:col-span-2">
            Dataset Path
            <input
              value={datasetPath}
              onChange={(e) => setDatasetPath(e.target.value)}
              className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-white"
            />
          </label>
          <label className="text-sm text-slate-400">
            Quality Floor
            <input
              type="number"
              min={0.5}
              max={1}
              step={0.05}
              value={qualityFloor}
              onChange={(e) => setQualityFloor(Number(e.target.value))}
              className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-white"
            />
          </label>
          <label className="text-sm text-slate-400">
            Max Prompts
            <input
              type="number"
              min={1}
              max={20}
              value={maxPrompts}
              onChange={(e) => setMaxPrompts(Number(e.target.value))}
              className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-white"
            />
          </label>
        </div>
        <div>
          <p className="mb-2 text-sm text-slate-400">Strategies</p>
          <div className="flex flex-wrap gap-3">
            {allStrategies.map((strategy) => (
              <label key={strategy} className="flex items-center gap-2 text-sm text-slate-300">
                <input
                  type="checkbox"
                  checked={strategies.includes(strategy)}
                  onChange={() => toggleStrategy(strategy)}
                  className="rounded border-slate-600"
                />
                {strategyLabels[strategy]}
              </label>
            ))}
          </div>
        </div>
        <button
          onClick={handleRun}
          disabled={loading}
          className="flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
        >
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
          Run Benchmark
        </button>
      </div>

      {loading && jobId && <JobProgressBar progress={jobProgress} label="Running benchmark..." />}
      {error && <ErrorBanner message={error} />}

      {report && (
        <>
          <div className="mb-6 grid grid-cols-1 gap-4 md:grid-cols-3">
            {report.strategies.map((item) => (
              <StatCard
                key={item.strategy}
                label={strategyLabels[item.strategy] ?? item.strategy}
                value={`${(item.metrics.average_quality * 100).toFixed(1)}% quality`}
                subtext={`Cost $${item.metrics.total_cost.toFixed(6)} · P95 ${item.metrics.p95_latency_ms.toFixed(0)} ms · Strong ${(item.metrics.strong_model_usage * 100).toFixed(0)}%`}
              />
            ))}
          </div>

          <ChartCard title="Strategy Comparison">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis dataKey="name" tick={{ fill: '#94a3b8', fontSize: 12 }} />
                <YAxis tick={{ fill: '#94a3b8', fontSize: 12 }} />
                <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #334155' }} />
                <Legend />
                <Bar dataKey="qualityRetention" name="Quality Retention %" fill="#22c55e" radius={[4, 4, 0, 0]} />
                <Bar dataKey="costReduction" name="Cost Reduction %" fill="#6366f1" radius={[4, 4, 0, 0]} />
                <Bar dataKey="routingAccuracy" name="Routing Accuracy %" fill="#f59e0b" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>
        </>
      )}

      {history.length > 0 && (
        <div className="mt-8 rounded-xl border border-slate-800 bg-slate-900/60 p-5">
          <h3 className="text-sm font-medium text-white">Recent Benchmarks</h3>
          <ul className="mt-3 space-y-2 text-sm">
            {history.slice(0, 8).map((item) => (
              <li key={item.id}>
                <button
                  onClick={() => loadReport(item.id)}
                  className="text-left text-slate-400 hover:text-brand-200"
                >
                  {new Date(item.created_at).toLocaleString()} · floor {(item.quality_floor * 100).toFixed(0)}% ·{' '}
                  {item.strategies.length} strategies
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
