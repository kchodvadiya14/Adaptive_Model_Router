import { useEffect, useState } from 'react';
import { FlaskConical, History, Play, X } from 'lucide-react';
import { Badge } from '../components/Badge';
import { Button } from '../components/Button';
import { Card } from '../components/Card';
import { EmptyState } from '../components/EmptyState';
import { ErrorBanner } from '../components/ErrorBanner';
import { Input } from '../components/Input';
import { JobProgressBar } from '../components/JobProgressBar';
import { PageHeader } from '../components/PageHeader';
import { Table, TableContainer, TBody, Td, Th, THead, Tr } from '../components/Table';
import { fetchExperimentReport, fetchExperiments, fetchExperimentStatus, startExperiment } from '../services/api';
import type { BenchmarkStrategy, ExperimentJobStatus, ExperimentManifest, ExperimentReport } from '../types';
import { formatTimestamp } from './benchmark/format';
import { StrategyGuide } from './benchmark/StrategyGuide';
import { ExperimentTypeGuide, RouterTypeGuide } from './experiments/ExperimentTypeGuide';
import {
  EXPERIMENT_TYPE_META,
  ROUTER_TYPE_ORDER,
  experimentTypeBadge,
  experimentTypeLabel,
  parseQualityFloors,
  type ExperimentType,
  type RouterTypeId,
} from './experiments/format';
import { ReportPanel } from './experiments/ReportPanel';

function statusLabel(status: ExperimentJobStatus['status'] | 'starting'): string {
  switch (status) {
    case 'starting':
      return 'Starting experiment…';
    case 'queued':
      return 'Queued';
    case 'running':
      return 'Running experiment…';
    case 'completed':
      return 'Completed';
    case 'failed':
      return 'Failed';
    default:
      return 'Running';
  }
}

export function ExperimentsPage() {
  // Configuration
  const [experimentType, setExperimentType] = useState<ExperimentType>('final_evaluation');
  const [name, setName] = useState('');
  const [datasetPath, setDatasetPath] = useState('data/benchmarks/routing_prompts.json');
  const [qualityFloor, setQualityFloor] = useState(0.9);
  const [maxPrompts, setMaxPrompts] = useState(8);
  const [strategies, setStrategies] = useState<BenchmarkStrategy[]>([
    'always_strong',
    'always_cheap',
    'adaptive_router',
  ]);
  const [qualityFloorsText, setQualityFloorsText] = useState('0.85, 0.9, 0.95');
  const [routerTypes, setRouterTypes] = useState<RouterTypeId[]>([...ROUTER_TYPE_ORDER]);

  // Run state
  const [running, setRunning] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [jobProgress, setJobProgress] = useState(0);
  const [jobStatus, setJobStatus] = useState<ExperimentJobStatus['status'] | 'starting' | null>(null);

  // Independent error channels
  const [creationError, setCreationError] = useState<string | null>(null);
  const [executionError, setExecutionError] = useState<string | null>(null);
  const [pollError, setPollError] = useState<string | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [historyError, setHistoryError] = useState<string | null>(null);

  // Results
  const [report, setReport] = useState<ExperimentReport | null>(null);
  const [comparisonReport, setComparisonReport] = useState<ExperimentReport | null>(null);
  const [history, setHistory] = useState<ExperimentManifest[]>([]);
  const [historyLoading, setHistoryLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setHistoryLoading(true);
    fetchExperiments()
      .then((items) => {
        if (!cancelled) {
          setHistory(items);
          setHistoryError(null);
        }
      })
      .catch(() => {
        if (!cancelled) setHistoryError('Could not load experiment history.');
      })
      .finally(() => {
        if (!cancelled) setHistoryLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [report]);

  // Polling: one interval per jobId, cleaned up on unmount or when jobId changes/clears.
  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;

    const poll = async () => {
      try {
        const status = await fetchExperimentStatus(jobId);
        if (cancelled) return;
        setJobProgress(status.progress);
        setJobStatus(status.status);
        if (status.status === 'completed' && status.report) {
          setReport(status.report);
          setRunning(false);
          setJobId(null);
          setJobStatus(null);
        } else if (status.status === 'failed') {
          setExecutionError(status.error ?? 'Experiment failed.');
          setRunning(false);
          setJobId(null);
          setJobStatus(null);
        }
      } catch {
        if (cancelled) return;
        setPollError('Lost connection while checking experiment status.');
        setRunning(false);
        setJobId(null);
        setJobStatus(null);
      }
    };

    void poll();
    const interval = setInterval(() => {
      void poll();
    }, 2000);

    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [jobId]);

  const toggleStrategy = (strategy: BenchmarkStrategy) => {
    if (running) return;
    setStrategies((prev) => (prev.includes(strategy) ? prev.filter((s) => s !== strategy) : [...prev, strategy]));
  };

  const toggleRouterType = (routerType: RouterTypeId) => {
    if (running) return;
    setRouterTypes((prev) => (prev.includes(routerType) ? prev.filter((r) => r !== routerType) : [...prev, routerType]));
  };

  const handleRun = async () => {
    if (experimentType === 'strategy_comparison' && strategies.length === 0) {
      setCreationError('Select at least one strategy.');
      return;
    }
    const parsedFloors = experimentType === 'quality_floor_sweep' ? parseQualityFloors(qualityFloorsText) : [];
    if (experimentType === 'quality_floor_sweep' && parsedFloors.length === 0) {
      setCreationError('Enter at least one quality floor between 0 and 1 (comma-separated).');
      return;
    }
    if (experimentType === 'router_comparison' && routerTypes.length === 0) {
      setCreationError('Select at least one router implementation.');
      return;
    }

    setRunning(true);
    setCreationError(null);
    setExecutionError(null);
    setPollError(null);
    setReport(null);
    setJobProgress(0);
    setJobStatus('starting');

    try {
      const job = await startExperiment({
        experiment_type: experimentType,
        name: name.trim() || EXPERIMENT_TYPE_META[experimentType].label,
        dataset_path: datasetPath,
        quality_floor: qualityFloor,
        max_prompts: maxPrompts,
        ...(experimentType === 'strategy_comparison' ? { strategies } : {}),
        ...(experimentType === 'quality_floor_sweep' ? { quality_floors: parsedFloors } : {}),
        ...(experimentType === 'router_comparison' ? { router_types: routerTypes } : {}),
      });
      setJobId(job.job_id);
      setJobProgress(job.progress);
      setJobStatus(job.status);
    } catch {
      setCreationError('Failed to start experiment. Ensure the backend is running.');
      setRunning(false);
      setJobStatus(null);
    }
  };

  const loadReport = async (reportId: string) => {
    if (running) return;
    try {
      setDetailError(null);
      setReport(await fetchExperimentReport(reportId));
    } catch {
      setDetailError('Failed to load experiment report.');
    }
  };

  const loadComparison = async (reportId: string) => {
    try {
      setDetailError(null);
      setComparisonReport(await fetchExperimentReport(reportId));
    } catch {
      setDetailError('Failed to load comparison report.');
    }
  };

  return (
    <div>
      <PageHeader
        title="Experiment Lab"
        description="Define, run, and compare controlled routing experiments against real model responses."
      />

      <Card className="mb-6">
        <h3 className="mb-1 text-sm font-medium text-ink-primary">Experiment configuration</h3>
        <p className="mb-4 text-xs text-ink-muted">Choose what to measure, then run it against a prompt dataset.</p>

        <p className="mb-2 text-xs text-ink-muted">Experiment type</p>
        <ExperimentTypeGuide selected={experimentType} disabled={running} onSelect={setExperimentType} />

        <div className="mb-4 mt-4 grid grid-cols-1 gap-4 md:grid-cols-3">
          <label className="text-xs text-ink-muted md:col-span-2">
            Run name
            <Input
              value={name}
              disabled={running}
              placeholder={EXPERIMENT_TYPE_META[experimentType].label}
              onChange={(event) => setName(event.target.value)}
              className="mt-1.5"
            />
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

          {experimentType === 'quality_floor_sweep' ? (
            <label className="text-xs text-ink-muted">
              Quality floors (comma-separated)
              <Input
                value={qualityFloorsText}
                disabled={running}
                onChange={(event) => setQualityFloorsText(event.target.value)}
                className="mt-1.5"
              />
            </label>
          ) : (
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
            </label>
          )}
        </div>

        {experimentType === 'strategy_comparison' && (
          <div className="mb-4">
            <p className="mb-2 text-xs text-ink-muted">Strategies</p>
            <StrategyGuide selected={strategies} disabled={running} onToggle={toggleStrategy} />
          </div>
        )}

        {experimentType === 'router_comparison' && (
          <div className="mb-4">
            <p className="mb-2 text-xs text-ink-muted">Router implementations</p>
            <RouterTypeGuide selected={routerTypes} disabled={running} onToggle={toggleRouterType} />
          </div>
        )}

        {experimentType === 'final_evaluation' && (
          <p className="mb-4 text-xs text-ink-muted">
            Runs strategy comparison, quality-floor ablation (85/90/95%), and router comparison across all
            implementations in one job.
          </p>
        )}

        {creationError && <ErrorBanner message={creationError} />}

        <div className="mt-2 flex flex-wrap items-center gap-3">
          <Button onClick={() => void handleRun()} loading={running} disabled={running}>
            {!running && <Play className="h-4 w-4" />}
            {running ? 'Running…' : 'Run Experiment'}
          </Button>
          {running && <Badge variant="info">{jobId ? `Job ${jobId.slice(0, 8)}` : 'Starting'}</Badge>}
        </div>
      </Card>

      {running && <JobProgressBar progress={jobProgress} label={statusLabel(jobStatus ?? 'running')} />}
      {executionError && <ErrorBanner message={executionError} />}
      {pollError && <ErrorBanner message={pollError} variant="warning" />}

      {!report && !running && !executionError && (
        <div className="mb-8">
          <EmptyState
            icon={FlaskConical}
            title="No results yet"
            description="Configure an experiment above and run it, or open a previous run from history below."
          />
        </div>
      )}

      {detailError && <ErrorBanner message={detailError} />}

      {report && (
        <div className="mb-8 space-y-6">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-sm font-medium text-ink-primary">Results</h3>
            {comparisonReport && (
              <Button variant="ghost" size="sm" onClick={() => setComparisonReport(null)}>
                <X className="h-3.5 w-3.5" />
                Clear comparison
              </Button>
            )}
          </div>

          <div className={comparisonReport ? 'grid grid-cols-1 gap-6 xl:grid-cols-2' : ''}>
            <ReportPanel report={report} heading={comparisonReport ? 'Primary run' : undefined} />
            {comparisonReport && <ReportPanel report={comparisonReport} heading="Comparison run" />}
          </div>
        </div>
      )}

      <section>
        <div className="mb-3 flex items-center gap-2">
          <History className="h-4 w-4 text-ink-secondary" />
          <h3 className="text-sm font-medium text-ink-primary">Experiment history</h3>
        </div>
        {historyError && <ErrorBanner message={historyError} variant="warning" />}
        {historyLoading || history.length > 0 ? (
          <TableContainer>
            <Table>
              <THead>
                <Tr>
                  <Th>Run</Th>
                  <Th>Type</Th>
                  <Th>Dataset</Th>
                  <Th />
                </Tr>
              </THead>
              <TBody>
                {historyLoading ? (
                  <Tr className="hover:bg-transparent">
                    <Td className="text-ink-muted">Loading experiment history…</Td>
                    <Td />
                    <Td />
                    <Td />
                  </Tr>
                ) : (
                  history.slice(0, 10).map((item) => {
                    const isPrimary = report?.id === item.id;
                    const isComparison = comparisonReport?.id === item.id;
                    return (
                      <Tr key={item.id} className={isPrimary ? 'bg-brand-500/10' : undefined}>
                        <Td>
                          <p className="font-medium text-ink-primary">{item.name}</p>
                          <p className="text-xs text-ink-muted">{formatTimestamp(item.created_at)}</p>
                        </Td>
                        <Td>
                          <Badge variant={experimentTypeBadge(item.experiment_type)}>
                            {experimentTypeLabel(item.experiment_type)}
                          </Badge>
                        </Td>
                        <Td className="max-w-[220px] truncate font-mono text-xs text-ink-secondary" title={item.dataset_path}>
                          {item.dataset_path}
                        </Td>
                        <Td>
                          <div className="flex flex-wrap gap-2">
                            <Button variant="ghost" size="sm" disabled={running} onClick={() => void loadReport(item.id)}>
                              {isPrimary ? 'Viewing' : 'Open'}
                            </Button>
                            {!isPrimary && (
                              <Button
                                variant="ghost"
                                size="sm"
                                disabled={running || !report}
                                onClick={() => void loadComparison(item.id)}
                              >
                                {isComparison ? 'Comparing' : 'Compare'}
                              </Button>
                            )}
                          </div>
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
            title="No experiments yet"
            description="Runs you complete are saved here so you can reopen or compare them later."
          />
        ) : null}
      </section>
    </div>
  );
}
