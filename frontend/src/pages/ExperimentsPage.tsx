import { useEffect, useState } from 'react';
import { FlaskConical, Loader2, Play } from 'lucide-react';
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
import { ErrorBanner } from '../components/ErrorBanner';
import { JobProgressBar } from '../components/JobProgressBar';
import { PageHeader } from '../components/PageHeader';
import { StatCard } from '../components/StatCard';
import {
  fetchExperimentReport,
  fetchExperiments,
  fetchExperimentStatus,
  startExperiment,
} from '../services/api';
import type { ExperimentManifest, ExperimentReport } from '../types';

export function ExperimentsPage() {
  const [maxPrompts, setMaxPrompts] = useState(8);
  const [qualityFloor, setQualityFloor] = useState(0.9);
  const [loading, setLoading] = useState(false);
  const [jobProgress, setJobProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<ExperimentReport | null>(null);
  const [history, setHistory] = useState<ExperimentManifest[]>([]);

  useEffect(() => {
    fetchExperiments().then(setHistory).catch(() => undefined);
  }, [report]);

  const handleRun = async () => {
    setLoading(true);
    setError(null);
    setReport(null);
    setJobProgress(0);
    try {
      const job = await startExperiment({
        experiment_type: 'final_evaluation',
        name: 'Final Evaluation Suite',
        dataset_path: 'data/benchmarks/sample_prompts.json',
        quality_floor: qualityFloor,
        max_prompts: maxPrompts,
        quality_floors: [0.85, 0.9, 0.95],
        router_types: ['rule_based', 'tfidf', 'embedding', 'bert'],
      });

      const poll = async () => {
        const status = await fetchExperimentStatus(job.job_id);
        setJobProgress(status.progress);
        if (status.status === 'completed' && status.report) {
          setReport(status.report);
          setLoading(false);
        } else if (status.status === 'failed') {
          setError(status.error ?? 'Experiment failed');
          setLoading(false);
        } else {
          setTimeout(poll, 2000);
        }
      };
      poll();
    } catch {
      setError('Failed to start final evaluation.');
      setLoading(false);
    }
  };

  const loadReport = async (reportId: string) => {
    try {
      setReport(await fetchExperimentReport(reportId));
    } catch {
      setError('Failed to load experiment report.');
    }
  };

  return (
    <div>
      <PageHeader
        title="Final Evaluation"
        description="Run the full research suite: strategy comparison, quality-floor ablation, and router comparison using mock-provider experiments."
      />

      <div className="mb-6 grid grid-cols-1 gap-4 rounded-xl border border-slate-800 bg-slate-900/60 p-5 md:grid-cols-3">
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
        <div className="flex items-end">
          <button
            onClick={handleRun}
            disabled={loading}
            className="flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
          >
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
            Run Final Evaluation
          </button>
        </div>
      </div>

      {loading && <JobProgressBar progress={jobProgress} label="Running final evaluation suite..." />}
      {error && <ErrorBanner message={error} />}

      {report && (
        <>
          <div className="mb-6 rounded-xl border border-slate-800 bg-slate-900/60 p-5">
            <h3 className="text-sm font-medium text-white">Summary</h3>
            <pre className="mt-3 whitespace-pre-wrap text-sm text-slate-300">{report.summary}</pre>
          </div>

          {report.sections.map((section) => {
            const chartData = section.variants.map((variant) => ({
              name: variant.name,
              quality: Number((variant.metrics.average_quality * 100).toFixed(1)),
              costReduction: Number((variant.metrics.cost_reduction * 100).toFixed(1)),
              strongUsage: Number((variant.metrics.strong_model_usage * 100).toFixed(1)),
            }));
            return (
              <div key={section.name} className="mb-6 rounded-xl border border-slate-800 bg-slate-900/60 p-5">
                <h3 className="mb-4 text-sm font-medium text-white">{section.name}</h3>
                <div className="mb-4 grid grid-cols-1 gap-3 md:grid-cols-3">
                  {section.variants.map((variant) => (
                    <StatCard
                      key={variant.name}
                      label={variant.name}
                      value={`${(variant.metrics.average_quality * 100).toFixed(1)}% quality`}
                      subtext={`Cost $${variant.metrics.average_cost.toFixed(6)} · Saved ${(variant.metrics.cost_reduction * 100).toFixed(1)}%`}
                    />
                  ))}
                </div>
                {chartData.length > 0 && (
                  <div className="h-64">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={chartData}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                        <XAxis dataKey="name" tick={{ fill: '#94a3b8', fontSize: 11 }} />
                        <YAxis tick={{ fill: '#94a3b8', fontSize: 12 }} />
                        <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #334155' }} />
                        <Legend />
                        <Bar dataKey="quality" name="Quality %" fill="#22c55e" radius={[4, 4, 0, 0]} />
                        <Bar dataKey="costReduction" name="Cost Reduction %" fill="#6366f1" radius={[4, 4, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                )}
              </div>
            );
          })}
        </>
      )}

      {history.length > 0 && (
        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-5">
          <h3 className="text-sm font-medium text-white">Previous Experiments</h3>
          <ul className="mt-3 space-y-2 text-sm">
            {history.slice(0, 8).map((item) => (
              <li key={item.id}>
                <button
                  onClick={() => loadReport(item.id)}
                  className="flex items-center gap-2 text-slate-400 hover:text-brand-200"
                >
                  <FlaskConical className="h-4 w-4" />
                  {item.name} · {new Date(item.created_at).toLocaleString()}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
