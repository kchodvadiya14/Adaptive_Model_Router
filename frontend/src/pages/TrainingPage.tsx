import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Cpu, MessageSquare, Play } from 'lucide-react';
import { Badge } from '../components/Badge';
import { Button } from '../components/Button';
import { Card } from '../components/Card';
import { EmptyState } from '../components/EmptyState';
import { ErrorBanner } from '../components/ErrorBanner';
import { Input } from '../components/Input';
import { JobProgressBar } from '../components/JobProgressBar';
import { PageHeader } from '../components/PageHeader';
import { Select } from '../components/Select';
import { StatCard } from '../components/StatCard';
import {
  fetchDatasets,
  fetchRouterStatus,
  fetchTrainedModels,
  fetchTrainingStatus,
  startTraining,
} from '../services/api';
import type { DatasetManifest, RouterStatusResponse, TrainedModelInfo, TrainingJobStatus } from '../types';
import { HowTrainingWorks } from './training/HowTrainingWorks';
import { TrainingHistoryTable } from './training/TrainingHistoryTable';
import { TrainingMetricsCharts } from './training/TrainingMetricsCharts';
import { TrainingPipeline } from './training/TrainingPipeline';
import {
  formatPercent,
  formatTimestamp,
  ROUTER_TYPE_LABEL,
  STATUS_BADGE,
  statusLabel,
  TrainingUIStatus,
} from './training/format';

type RouterType = TrainedModelInfo['router_type'];

export function TrainingPage() {
  const [datasets, setDatasets] = useState<DatasetManifest[]>([]);
  const [datasetsLoading, setDatasetsLoading] = useState(true);
  const [datasetsError, setDatasetsError] = useState<string | null>(null);

  const [models, setModels] = useState<TrainedModelInfo[]>([]);
  const [modelsError, setModelsError] = useState<string | null>(null);

  const [routerStatus, setRouterStatus] = useState<RouterStatusResponse | null>(null);

  const [datasetId, setDatasetId] = useState('');
  const [routerType, setRouterType] = useState<RouterType>('tfidf');
  const [threshold, setThreshold] = useState(0.6);

  const [status, setStatus] = useState<TrainingUIStatus>('idle');
  const [jobProgress, setJobProgress] = useState(0);
  const [trainError, setTrainError] = useState<string | null>(null);
  const [result, setResult] = useState<TrainedModelInfo | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);

  const loadTrainedModels = useCallback(async () => {
    try {
      const data = await fetchTrainedModels();
      setModels(data);
      setModelsError(null);
    } catch {
      setModelsError('Failed to load trained router history.');
    }
  }, []);

  useEffect(() => {
    setDatasetsLoading(true);
    fetchDatasets()
      .then((data) => {
        setDatasets(data);
        setDatasetsError(null);
        if (data.length > 0) setDatasetId((current) => current || data[0].id);
      })
      .catch(() => setDatasetsError('Failed to load datasets.'))
      .finally(() => setDatasetsLoading(false));

    fetchRouterStatus()
      .then(setRouterStatus)
      .catch(() => setRouterStatus(null));

    loadTrainedModels();
  }, [loadTrainedModels]);

  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;

    const poll = async () => {
      try {
        const job: TrainingJobStatus = await fetchTrainingStatus(jobId);
        if (cancelled) return;
        setJobProgress(job.progress);
        setStatus(job.status);
        if (job.status === 'completed' && job.result) {
          setResult(job.result);
          setJobId(null);
          void loadTrainedModels();
        } else if (job.status === 'failed') {
          setTrainError(job.error ?? 'Training failed.');
          setJobId(null);
        }
      } catch {
        if (cancelled) return;
        setTrainError('Failed to poll training status.');
        setJobId(null);
        setStatus('failed');
      }
    };

    void poll();
    const interval = setInterval(() => void poll(), 2000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [jobId, loadTrainedModels]);

  const running = status === 'starting' || status === 'queued' || status === 'running';

  const handleTrain = async () => {
    if (!datasetId || running) return;
    setStatus('starting');
    setTrainError(null);
    setResult(null);
    setJobProgress(0);
    try {
      const job = await startTraining({
        dataset_id: datasetId,
        router_type: routerType,
        routing_threshold: threshold,
      });
      setJobId(job.job_id);
      setJobProgress(job.progress);
      setStatus(job.status);
    } catch {
      setTrainError('Failed to start training. Check that the dataset has enough labeled records.');
      setStatus('failed');
    }
  };

  const selectedDataset = useMemo(
    () => datasets.find((dataset) => dataset.id === datasetId) ?? null,
    [datasets, datasetId],
  );

  const datasetsById = useMemo(() => new Map(datasets.map((dataset) => [dataset.id, dataset])), [datasets]);
  const resultDataset = result ? datasetsById.get(result.dataset_id) : undefined;

  return (
    <div>
      <PageHeader
        title="Router Training & Model Improvement"
        description="Train a router model from a preference dataset, then activate it so the gateway routes using its predictions."
        action={
          <Link to="/chat">
            <Button variant="secondary">
              <MessageSquare className="h-4 w-4" />
              Test in Chat
            </Button>
          </Link>
        }
      />

      <div className="mb-6">
        <TrainingPipeline />
      </div>

      <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Router in use" value={routerStatus ? routerStatus.router_type : '—'} />
        <StatCard label="Quality floor" value={routerStatus ? formatPercent(routerStatus.quality_floor, 0) : '—'} />
        <StatCard
          label="Enabled models"
          value={routerStatus ? `${routerStatus.enabled_models} / ${routerStatus.total_models}` : '—'}
        />
        <StatCard label="Trained routers" value={models.length} subtext="Across all runs" />
      </div>

      <div className="mb-6">
        <HowTrainingWorks />
      </div>

      {datasetsError && <ErrorBanner message={datasetsError} />}

      {!datasetsLoading && datasets.length === 0 && !datasetsError ? (
        <EmptyState
          icon={Cpu}
          title="No datasets available to train from"
          description="Generate a preference dataset first, then come back here to train a router."
        />
      ) : (
        <Card className="mb-6">
          <h3 className="mb-1 text-sm font-medium text-ink-primary">Train a new router</h3>
          <p className="mb-4 text-xs text-ink-muted">
            Fits a classifier on the selected dataset's preference labels and evaluates it on a held-out split.
          </p>
          <div className="mb-4 grid grid-cols-1 gap-4 md:grid-cols-4">
            <label className="text-xs text-ink-muted md:col-span-2">
              Dataset
              <Select
                value={datasetId}
                disabled={running || datasetsLoading}
                onChange={(event) => setDatasetId(event.target.value)}
                className="mt-1.5"
              >
                {datasets.map((dataset) => (
                  <option key={dataset.id} value={dataset.id}>
                    {dataset.name} ({dataset.record_count} records)
                  </option>
                ))}
              </Select>
            </label>
            <label className="text-xs text-ink-muted">
              Router type
              <Select
                value={routerType}
                disabled={running}
                onChange={(event) => setRouterType(event.target.value as RouterType)}
                className="mt-1.5"
              >
                <option value="tfidf">TF-IDF + Logistic Regression</option>
                <option value="embedding">Embedding + Classifier</option>
                <option value="bert">BERT-style MLP</option>
              </Select>
            </label>
            <label className="text-xs text-ink-muted">
              Routing threshold
              <Input
                type="number"
                min={0.1}
                max={1}
                step={0.05}
                value={threshold}
                disabled={running}
                onChange={(event) => setThreshold(Number(event.target.value))}
                className="mt-1.5"
              />
            </label>
          </div>

          {selectedDataset && (
            <div className="mb-4 flex flex-wrap gap-x-6 gap-y-1 rounded-lg bg-surface-3/40 px-3 py-2 text-xs text-ink-secondary">
              <span>
                <span className="text-ink-muted">Records:</span> {selectedDataset.record_count}
              </span>
              <span>
                <span className="text-ink-muted">Judge:</span> {selectedDataset.judge_provider}
              </span>
              <span>
                <span className="text-ink-muted">Quality floor:</span> {formatPercent(selectedDataset.quality_floor, 0)}
              </span>
              <span>
                <span className="text-ink-muted">Created:</span> {formatTimestamp(selectedDataset.created_at)}
              </span>
            </div>
          )}

          <div className="flex flex-wrap items-center gap-3">
            <Button onClick={() => void handleTrain()} loading={running} disabled={running || !datasetId}>
              {!running && <Play className="h-4 w-4" />}
              {running ? 'Training…' : 'Start training'}
            </Button>
            <Badge variant={STATUS_BADGE[status]}>{statusLabel(status)}</Badge>
          </div>
        </Card>
      )}

      {running && <JobProgressBar progress={jobProgress} label={statusLabel(status)} />}
      {trainError && <ErrorBanner message={trainError} />}

      {result ? (
        <section className="mb-8">
          <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
            <h3 className="text-sm font-medium text-ink-primary">Training result</h3>
            <p className="text-xs text-ink-muted">{formatTimestamp(result.created_at)}</p>
          </div>

          <div className="mb-4 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard label="Router type" value={ROUTER_TYPE_LABEL[result.router_type]} />
            <StatCard label="Dataset" value={resultDataset?.name ?? result.dataset_id} />
            <StatCard label="Samples" value={result.samples.toLocaleString()} subtext={`Threshold ${result.threshold}`} />
            <StatCard label="Test accuracy" value={formatPercent(result.metrics.test_accuracy)} />
          </div>

          <div className="mb-4">
            <TrainingMetricsCharts metrics={result.metrics} />
          </div>

          <Card>
            <p className="text-xs text-ink-muted">Artifact</p>
            <p className="mt-1 break-all font-mono text-xs text-ink-secondary">{result.model_path}</p>
            <p className="mt-3 text-sm text-ink-secondary">
              To route traffic with this model, set{' '}
              <code className="rounded bg-surface-3 px-1 py-0.5 text-xs text-brand-300">
                ROUTER_TYPE={result.router_type}
              </code>{' '}
              in the backend's <code className="rounded bg-surface-3 px-1 py-0.5 text-xs text-brand-300">.env</code>{' '}
              and restart it. The gateway loads the most recently trained artifact of that type.
            </p>
          </Card>
        </section>
      ) : status === 'idle' ? (
        <div className="mb-8">
          <EmptyState
            icon={Cpu}
            title="No completed training run yet"
            description="Start training above to fit a router and see its evaluation metrics here."
          />
        </div>
      ) : null}

      <section>
        <h3 className="mb-3 text-sm font-medium text-ink-primary">Trained router history</h3>
        {modelsError && <ErrorBanner message={modelsError} variant="warning" />}
        {!modelsError && models.length === 0 ? (
          <EmptyState
            icon={Cpu}
            title="No trained routers yet"
            description="Completed training runs will appear here so you can compare them over time."
          />
        ) : !modelsError ? (
          <TrainingHistoryTable models={models} datasetsById={datasetsById} />
        ) : null}
      </section>
    </div>
  );
}
