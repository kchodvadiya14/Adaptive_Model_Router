import { useEffect, useMemo, useState } from 'react';
import { FlaskConical, History, Play } from 'lucide-react';
import { Badge } from '../components/Badge';
import { Button } from '../components/Button';
import { Card } from '../components/Card';
import { EmptyState } from '../components/EmptyState';
import { ErrorBanner } from '../components/ErrorBanner';
import { Input } from '../components/Input';
import { JobProgressBar } from '../components/JobProgressBar';
import { PageHeader } from '../components/PageHeader';
import { Table, TableContainer, TBody, Td, Th, THead, Tr } from '../components/Table';
import {
  fetchBenchmarkReport,
  fetchBenchmarkStatus,
  fetchBenchmarks,
  startBenchmark,
} from '../services/api';
import type { BenchmarkJobStatus, BenchmarkReport, BenchmarkStrategy } from '../types';
import { ComparisonCharts } from './benchmark/ComparisonCharts';
import { ComparisonTable, SampleTable } from './benchmark/ComparisonTable';
import { Interpretation } from './benchmark/Interpretation';
import { StrategyGuide } from './benchmark/StrategyGuide';
import {
  STRATEGY_ORDER,
  formatCost,
  formatMs,
  formatPercent,
  formatTimestamp,
  strategyBadge,
  strategyLabel,
  toChartRows,
} from './benchmark/format';

const ALL_STRATEGIES: BenchmarkStrategy[] = [...STRATEGY_ORDER];

function statusLabel(status: BenchmarkJobStatus['status'] | 'starting'): string {
  switch (status) {
    case 'starting':
      return 'Starting evaluation…';
    case 'queued':
      return 'Queued';
    case 'running':
      return 'Evaluating strategies…';
    case 'completed':
      return 'Completed';
    case 'failed':
      return 'Failed';
    default:
      return 'Running';
  }
}

export function BenchmarkPage() {
  const [datasetPath, setDatasetPath] = useState('data/benchmarks/routing_prompts.json');
  const [qualityFloor, setQualityFloor] = useState(0.9);
  const [maxPrompts, setMaxPrompts] = useState(8);
  const [strategies, setStrategies] = useState<BenchmarkStrategy[]>(ALL_STRATEGIES);

  const [jobId, setJobId] = useState<string | null>(null);
  const [jobProgress, setJobProgress] = useState(0);
  const [jobStatus, setJobStatus] = useState<BenchmarkJobStatus['status'] | 'starting' | null>(null);
  const [running, setRunning] = useState(false);

  const [error, setError] = useState<string | null>(null);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [report, setReport] = useState<BenchmarkReport | null>(null);
  const [history, setHistory] = useState<BenchmarkReport[]>([]);
  const [historyLoading, setHistoryLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setHistoryLoading(true);
    fetchBenchmarks()
      .then((items) => {
        if (!cancelled) {
          setHistory(items);
          setHistoryError(null);
        }
      })
      .catch(() => {
        if (!cancelled) setHistoryError('Could not load recent benchmarks.');
      })
      .finally(() => {
        if (!cancelled) setHistoryLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [report]);

  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;

    const poll = async () => {
      try {
        const status = await fetchBenchmarkStatus(jobId);
        if (cancelled) return;
        setJobProgress(status.progress);
        setJobStatus(status.status);
        if (status.status === 'completed' && status.report) {
          setReport(status.report);
          setRunning(false);
          setJobId(null);
          setJobStatus(null);
        } else if (status.status === 'failed') {
          setError(status.error ?? 'Benchmark failed');
          setRunning(false);
          setJobId(null);
          setJobStatus(null);
        }
      } catch {
        if (cancelled) return;
        setError('Failed to poll benchmark status');
        setRunning(false);
        setJobId(null);
        setJobStatus(null);
      }
    };

    void poll();
    const interval = setInterval(() => {
      void poll();
    }, 1500);

    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [jobId]);

  const toggleStrategy = (strategy: BenchmarkStrategy) => {
    if (running) return;
    setStrategies((prev) =>
      prev.includes(strategy) ? prev.filter((item) => item !== strategy) : [...prev, strategy],
    );
  };

  const handleRun = async () => {
    if (strategies.length === 0) {
      setError('Select at least one strategy.');
      return;
    }
    setRunning(true);
    setError(null);
    setReport(null);
    setJobProgress(0);
    setJobStatus('starting');
    try {
      const job = await startBenchmark({
        dataset_path: datasetPath,
        quality_floor: qualityFloor,
        max_prompts: maxPrompts,
        strategies,
      });
      setJobId(job.job_id);
      setJobProgress(job.progress);
      setJobStatus(job.status);
    } catch {
      setError('Failed to start benchmark. Ensure the backend is running and strong/small models are enabled.');
      setRunning(false);
      setJobStatus(null);
    }
  };

  const loadReport = async (reportId: string) => {
    if (running) return;
    try {
      setError(null);
      setReport(await fetchBenchmarkReport(reportId));
    } catch {
      setError('Failed to load benchmark report.');
    }
  };

  const chartRows = useMemo(() => (report ? toChartRows(report) : []), [report]);

  return (
    <div>
      <PageHeader
        title="Model Routing Evaluation"
        description="How does Adaptive Routing compare with fixed Always Strong and Always Cheap strategies on the same prompt set?"
      />

      <Card className="mb-6">
        <h3 className="mb-1 text-sm font-medium text-ink-primary">Benchmark controls</h3>
        <p className="mb-4 text-xs text-ink-muted">
          All selected strategies run against the same dataset, quality floor, and prompt limit.
        </p>
        <div className="mb-4 grid grid-cols-1 gap-4 md:grid-cols-3">
          <label className="text-xs text-ink-muted md:col-span-2">
            Dataset path
            <Input
              value={datasetPath}
              disabled={running}
              onChange={(event) => setDatasetPath(event.target.value)}
              className="mt-1.5"
            />
          </label>
          <label className="text-xs text-ink-muted">
            Quality floor
            <Input
              type="number"
              min={0}
              max={1}
              step={0.05}
              value={qualityFloor}
              disabled={running}
              onChange={(event) => setQualityFloor(Number(event.target.value))}
              className="mt-1.5"
            />
            <span className="mt-1 block text-[11px] text-ink-disabled">
              {formatPercent(qualityFloor, 0)} minimum quality target for the router
            </span>
          </label>
          <label className="text-xs text-ink-muted">
            Max prompts
            <Input
              type="number"
              min={1}
              max={200}
              value={maxPrompts}
              disabled={running}
              onChange={(event) => setMaxPrompts(Number(event.target.value))}
              className="mt-1.5"
            />
          </label>
        </div>

        <p className="mb-2 text-xs text-ink-muted">Strategies</p>
        <StrategyGuide selected={strategies} disabled={running} onToggle={toggleStrategy} />

        <div className="mt-4 flex flex-wrap items-center gap-3">
          <Button onClick={() => void handleRun()} loading={running} disabled={running || strategies.length === 0}>
            {!running && <Play className="h-4 w-4" />}
            {running ? 'Running…' : 'Run benchmark'}
          </Button>
          {running && <Badge variant="info">{jobId ? `Job ${jobId.slice(0, 8)}` : 'Starting'}</Badge>}
        </div>
      </Card>

      {running && <JobProgressBar progress={jobProgress} label={statusLabel(jobStatus ?? 'running')} />}
      {error && <ErrorBanner message={error} />}

      {!report && !running && (
        <div className="mb-8">
          <EmptyState
            icon={FlaskConical}
            title="No evaluation results yet"
            description="Choose strategies, then run a benchmark to compare Adaptive Routing with fixed model baselines."
          />
        </div>
      )}

      {report && (
        <div className="mb-8 space-y-8">
          <section>
            <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
              <h3 className="text-sm font-medium text-ink-primary">Results</h3>
              <p className="text-xs text-ink-muted">
                {formatTimestamp(report.created_at)} · {report.dataset_path} · floor {formatPercent(report.quality_floor, 0)}
              </p>
            </div>
            <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
              {report.strategies.map((item) => (
                <Card key={item.strategy}>
                  <div className="mb-3 flex items-center justify-between gap-2">
                    <Badge variant={strategyBadge(item.strategy)}>{strategyLabel(item.strategy)}</Badge>
                    <span className="text-xs text-ink-muted">{item.metrics.total_requests} requests</span>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <StatMini label="Avg. quality" value={formatPercent(item.metrics.average_quality)} />
                    <StatMini label="Avg. cost" value={formatCost(item.metrics.average_cost)} />
                    <StatMini label="Avg. latency" value={formatMs(item.metrics.average_latency_ms)} />
                    <StatMini label="Quality retention" value={formatPercent(item.metrics.quality_retention)} />
                  </div>
                  <p className="mt-3 text-xs text-ink-muted">
                    Total {formatCost(item.metrics.total_cost)} · P95 {formatMs(item.metrics.p95_latency_ms)} · Strong
                    usage {formatPercent(item.metrics.strong_model_usage, 0)}
                  </p>
                </Card>
              ))}
            </div>
          </section>

          <section>
            <h3 className="mb-3 text-sm font-medium text-ink-primary">Comparison</h3>
            <div className="mb-4">
              <ComparisonCharts rows={chartRows} />
            </div>
            <ComparisonTable report={report} />
          </section>

          <section>
            <Interpretation report={report} />
          </section>

          <SampleTable report={report} />
        </div>
      )}

      <section>
        <div className="mb-3 flex items-center gap-2">
          <History className="h-4 w-4 text-ink-secondary" />
          <h3 className="text-sm font-medium text-ink-primary">Recent benchmarks</h3>
        </div>
        {historyError && <ErrorBanner message={historyError} variant="warning" />}
        {historyLoading || history.length > 0 ? (
          <TableContainer>
            <Table>
              <THead>
                <Tr>
                  <Th>Run</Th>
                  <Th>Dataset</Th>
                  <Th>Quality floor</Th>
                  <Th>Strategies</Th>
                  <Th />
                </Tr>
              </THead>
              <TBody>
                {historyLoading ? (
                  <Tr className="hover:bg-transparent">
                    <Td className="text-ink-muted">Loading recent reports…</Td>
                    <Td />
                    <Td />
                    <Td />
                    <Td />
                  </Tr>
                ) : (
                  history.slice(0, 8).map((item) => {
                    const selected = report?.id === item.id;
                    return (
                      <Tr key={item.id} className={selected ? 'bg-brand-500/10' : undefined}>
                        <Td className="text-ink-secondary">{formatTimestamp(item.created_at)}</Td>
                        <Td className="max-w-[240px] truncate font-mono text-xs text-ink-secondary" title={item.dataset_path}>
                          {item.dataset_path}
                        </Td>
                        <Td className="text-ink-secondary">{formatPercent(item.quality_floor, 0)}</Td>
                        <Td>
                          <div className="flex flex-wrap gap-1">
                            {item.strategies.map((strategy) => (
                              <Badge key={strategy.strategy} variant={strategyBadge(strategy.strategy)}>
                                {strategyLabel(strategy.strategy)}
                              </Badge>
                            ))}
                          </div>
                        </Td>
                        <Td>
                          <Button variant="ghost" size="sm" disabled={running} onClick={() => void loadReport(item.id)}>
                            {selected ? 'Viewing' : 'Open'}
                          </Button>
                        </Td>
                      </Tr>
                    );
                  })
                )}
              </TBody>
            </Table>
          </TableContainer>
        ) : !historyError ? (
          <EmptyState
            icon={History}
            title="No saved reports"
            description="Completed evaluations appear here so you can reopen a previous run."
          />
        ) : null}
      </section>
    </div>
  );
}

function StatMini({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[11px] text-ink-muted">{label}</p>
      <p className="mt-0.5 text-sm font-medium text-ink-primary">{value}</p>
    </div>
  );
}
