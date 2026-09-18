import { useCallback, useEffect, useMemo, useState } from 'react';
import { Database, Gauge, Scale, Sparkles } from 'lucide-react';
import { Badge } from '../components/Badge';
import { Card } from '../components/Card';
import { EmptyState } from '../components/EmptyState';
import { ErrorBanner } from '../components/ErrorBanner';
import { JobProgressBar } from '../components/JobProgressBar';
import { PageHeader } from '../components/PageHeader';
import { StatCard } from '../components/StatCard';
import {
  fetchDatasetGenerationStatus,
  fetchDatasetRecords,
  fetchDatasets,
  startDatasetGeneration,
  submitHumanEval,
} from '../services/api';
import type { DatasetGenerateJobStatus, DatasetManifest, PreferenceRecord } from '../types';
import { DatasetTable } from './dataset/DatasetTable';
import { computeBreakdown, formatTaskType, formatTimestamp, TIER_BADGE } from './dataset/format';
import { GenerateDatasetCard } from './dataset/GenerateDatasetCard';
import { RecordReviewModal } from './dataset/RecordReviewModal';
import { RecordsTable } from './dataset/RecordsTable';

const PAGE_SIZE = 10;

function statusLabel(status: DatasetGenerateJobStatus['status'] | 'starting'): string {
  switch (status) {
    case 'starting':
      return 'Starting generation…';
    case 'queued':
      return 'Queued';
    case 'running':
      return 'Collecting tier responses and scoring with the judge…';
    case 'completed':
      return 'Completed';
    case 'failed':
      return 'Failed';
    default:
      return 'Running';
  }
}

export function DatasetPage() {
  const [datasets, setDatasets] = useState<DatasetManifest[]>([]);
  const [datasetsLoading, setDatasetsLoading] = useState(true);
  const [datasetsError, setDatasetsError] = useState<string | null>(null);

  const [selectedId, setSelectedId] = useState<string>('');
  const [fullRecords, setFullRecords] = useState<PreferenceRecord[]>([]);
  const [recordsLoading, setRecordsLoading] = useState(false);
  const [recordsError, setRecordsError] = useState<string | null>(null);

  const [search, setSearch] = useState('');
  const [taskFilter, setTaskFilter] = useState('');
  const [page, setPage] = useState(0);

  const [reviewRecord, setReviewRecord] = useState<PreferenceRecord | null>(null);
  const [reviewSubmitting, setReviewSubmitting] = useState(false);
  const [reviewError, setReviewError] = useState<string | null>(null);

  const [sourcePath, setSourcePath] = useState('data/benchmarks/routing_prompts.json');
  const [qualityFloor, setQualityFloor] = useState(0.9);
  const [maxPrompts, setMaxPrompts] = useState(8);
  const [jobId, setJobId] = useState<string | null>(null);
  const [jobProgress, setJobProgress] = useState(0);
  const [jobStatus, setJobStatus] = useState<DatasetGenerateJobStatus['status'] | 'starting' | null>(null);
  const [running, setRunning] = useState(false);
  const [generateError, setGenerateError] = useState<string | null>(null);
  const [lastGenerated, setLastGenerated] = useState<DatasetManifest | null>(null);

  const loadDatasets = useCallback(async (): Promise<DatasetManifest[]> => {
    setDatasetsLoading(true);
    try {
      const data = await fetchDatasets();
      setDatasets(data);
      setDatasetsError(null);
      return data;
    } catch {
      setDatasetsError('Failed to load datasets. Ensure the backend is running.');
      return [];
    } finally {
      setDatasetsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadDatasets().then((data) => {
      if (data.length > 0) setSelectedId((current) => current || data[0].id);
    });
  }, [loadDatasets]);

  const selectedManifest = useMemo(
    () => datasets.find((dataset) => dataset.id === selectedId) ?? null,
    [datasets, selectedId],
  );

  useEffect(() => {
    if (!selectedManifest) {
      setFullRecords([]);
      return;
    }
    let cancelled = false;
    setRecordsLoading(true);
    setRecordsError(null);
    fetchDatasetRecords(selectedManifest.id, { offset: 0, limit: Math.max(selectedManifest.record_count, 1) })
      .then((data) => {
        if (!cancelled) setFullRecords(data.records);
      })
      .catch(() => {
        if (!cancelled) {
          setRecordsError('Failed to load records for this dataset.');
          setFullRecords([]);
        }
      })
      .finally(() => {
        if (!cancelled) setRecordsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedManifest]);

  useEffect(() => {
    setSearch('');
    setTaskFilter('');
    setPage(0);
  }, [selectedId]);

  useEffect(() => {
    setPage(0);
  }, [search, taskFilter]);

  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;

    const poll = async () => {
      try {
        const status = await fetchDatasetGenerationStatus(jobId);
        if (cancelled) return;
        setJobProgress(status.progress);
        setJobStatus(status.status);
        if (status.status === 'completed' && status.manifest) {
          setLastGenerated(status.manifest);
          setRunning(false);
          setJobId(null);
          setJobStatus(null);
          await loadDatasets();
          if (!cancelled) setSelectedId(status.manifest.id);
        } else if (status.status === 'failed') {
          setGenerateError(status.error ?? 'Dataset generation failed.');
          setRunning(false);
          setJobId(null);
          setJobStatus(null);
        }
      } catch {
        if (cancelled) return;
        setGenerateError('Failed to poll dataset generation status.');
        setRunning(false);
        setJobId(null);
        setJobStatus(null);
      }
    };

    void poll();
    const interval = setInterval(() => void poll(), 1500);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [jobId, loadDatasets]);

  const handleGenerate = async () => {
    setRunning(true);
    setGenerateError(null);
    setLastGenerated(null);
    setJobProgress(0);
    setJobStatus('starting');
    try {
      const job = await startDatasetGeneration({
        source_path: sourcePath,
        name: `dataset_${Date.now()}`,
        quality_floor: qualityFloor,
        max_prompts: maxPrompts,
      });
      setJobId(job.job_id);
      setJobProgress(job.progress);
      setJobStatus(job.status);
    } catch {
      setGenerateError('Failed to start dataset generation.');
      setRunning(false);
      setJobStatus(null);
    }
  };

  const handleReviewSubmit = async (form: {
    small_score: number;
    medium_score: number;
    strong_score: number;
    preferred_model: 'small' | 'medium' | 'strong';
    notes: string;
  }) => {
    if (!selectedManifest || !reviewRecord) return;
    setReviewSubmitting(true);
    setReviewError(null);
    try {
      const updated = await submitHumanEval(selectedManifest.id, {
        record_id: reviewRecord.id,
        small_score: form.small_score,
        medium_score: form.medium_score,
        strong_score: form.strong_score,
        preferred_model: form.preferred_model,
        notes: form.notes || undefined,
      });
      setFullRecords((prev) => prev.map((record) => (record.id === updated.id ? updated : record)));
      setReviewRecord(null);
    } catch {
      setReviewError('Failed to save human evaluation.');
    } finally {
      setReviewSubmitting(false);
    }
  };

  const breakdown = useMemo(() => computeBreakdown(fullRecords), [fullRecords]);

  const filteredRecords = useMemo(() => {
    const query = search.trim().toLowerCase();
    return fullRecords.filter((record) => {
      if (taskFilter && record.task_type !== taskFilter) return false;
      if (query && !record.prompt.toLowerCase().includes(query)) return false;
      return true;
    });
  }, [fullRecords, search, taskFilter]);

  const pagedRecords = filteredRecords.slice(page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE);

  const totalRecords = datasets.reduce((sum, dataset) => sum + dataset.record_count, 0);
  const distinctJudges = Array.from(new Set(datasets.map((dataset) => dataset.judge_provider)));
  const latestDataset = datasets.reduce<DatasetManifest | null>((latest, dataset) => {
    if (!latest) return dataset;
    return new Date(dataset.created_at) > new Date(latest.created_at) ? dataset : latest;
  }, null);

  return (
    <div>
      <PageHeader
        title="Routing Dataset Management"
        description="Preference datasets pair each prompt with small/medium/strong tier responses and judge scores — the training and evaluation data behind the adaptive router."
      />

      {datasetsError && <ErrorBanner message={datasetsError} />}

      {!datasetsLoading && datasets.length === 0 && !datasetsError ? (
        <EmptyState
          icon={Database}
          title="No datasets yet"
          description="Generate your first preference dataset below to start building training and evaluation data."
        />
      ) : (
        <>
          <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard label="Datasets" value={datasetsLoading ? '—' : datasets.length} />
            <StatCard label="Total records" value={datasetsLoading ? '—' : totalRecords.toLocaleString()} />
            <StatCard
              label="Judge sources"
              value={datasetsLoading ? '—' : distinctJudges.length}
              subtext={datasetsLoading ? undefined : distinctJudges.join(', ') || undefined}
            />
            <StatCard
              label="Most recent"
              value={datasetsLoading || !latestDataset ? '—' : latestDataset.name}
              subtext={latestDataset ? formatTimestamp(latestDataset.created_at) : undefined}
            />
          </div>

          <section className="mb-8">
            <h3 className="mb-3 text-sm font-medium text-ink-primary">Datasets</h3>
            {datasetsLoading ? (
              <Card>
                <p className="text-sm text-ink-muted">Loading datasets…</p>
              </Card>
            ) : (
              <DatasetTable datasets={datasets} selectedId={selectedId} onSelect={setSelectedId} />
            )}
          </section>

          {selectedManifest && (
            <section className="mb-8">
              <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
                <div>
                  <h3 className="text-sm font-medium text-ink-primary">{selectedManifest.name}</h3>
                  <p className="text-xs text-ink-muted">
                    {shortDescription(selectedManifest)} · created {formatTimestamp(selectedManifest.created_at)}
                  </p>
                </div>
              </div>

              {recordsError && <ErrorBanner message={recordsError} variant="warning" />}

              {recordsLoading ? (
                <Card>
                  <p className="text-sm text-ink-muted">Loading records…</p>
                </Card>
              ) : fullRecords.length === 0 ? (
                <EmptyState
                  icon={Database}
                  title="No records in this dataset"
                  description="This dataset manifest exists, but no preference records were found."
                />
              ) : (
                <>
                  <div className="mb-5 grid grid-cols-1 gap-4 md:grid-cols-3">
                    <Card>
                      <div className="mb-2 flex items-center gap-2 text-ink-secondary">
                        <Gauge className="h-4 w-4" />
                        <p className="text-xs font-medium uppercase tracking-wide">Task coverage</p>
                      </div>
                      <div className="flex flex-wrap gap-1.5">
                        {breakdown.taskTypes.map((item) => (
                          <Badge key={item.key} variant="neutral">
                            {formatTaskType(item.key)} · {item.count}
                          </Badge>
                        ))}
                      </div>
                    </Card>
                    <Card>
                      <div className="mb-2 flex items-center gap-2 text-ink-secondary">
                        <Scale className="h-4 w-4" />
                        <p className="text-xs font-medium uppercase tracking-wide">Preferred-tier distribution</p>
                      </div>
                      <div className="flex flex-wrap gap-1.5">
                        {(['small', 'medium', 'strong'] as const).map((tier) => (
                          <Badge key={tier} variant={TIER_BADGE[tier]}>
                            {tier} · {breakdown.preferredModel[tier]}
                          </Badge>
                        ))}
                      </div>
                      <p className="mt-2 text-xs text-ink-muted">
                        How often a cheaper tier already met the quality floor — signal for how much this dataset
                        teaches the router to save cost.
                      </p>
                    </Card>
                    <Card>
                      <div className="mb-2 flex items-center gap-2 text-ink-secondary">
                        <Sparkles className="h-4 w-4" />
                        <p className="text-xs font-medium uppercase tracking-wide">Evaluation relevance</p>
                      </div>
                      <div className="flex flex-wrap gap-1.5">
                        {Object.entries(breakdown.evaluationSource).map(([source, count]) => (
                          <Badge key={source} variant="neutral">
                            {source} · {count}
                          </Badge>
                        ))}
                      </div>
                      <p className="mt-2 text-xs text-ink-muted">
                        Judge: {selectedManifest.judge_provider} · quality floor{' '}
                        {(selectedManifest.quality_floor * 100).toFixed(0)}%
                      </p>
                    </Card>
                  </div>

                  <RecordsTable
                    records={pagedRecords}
                    taskTypes={breakdown.taskTypes.map((item) => item.key)}
                    search={search}
                    onSearchChange={setSearch}
                    taskFilter={taskFilter}
                    onTaskFilterChange={setTaskFilter}
                    page={page}
                    pageSize={PAGE_SIZE}
                    totalFiltered={filteredRecords.length}
                    onPageChange={setPage}
                    onReview={setReviewRecord}
                  />
                </>
              )}
            </section>
          )}
        </>
      )}

      <section>
        <h3 className="mb-3 text-sm font-medium text-ink-primary">Generate dataset</h3>
        <GenerateDatasetCard
          sourcePath={sourcePath}
          onSourcePathChange={setSourcePath}
          qualityFloor={qualityFloor}
          onQualityFloorChange={setQualityFloor}
          maxPrompts={maxPrompts}
          onMaxPromptsChange={setMaxPrompts}
          running={running}
          onGenerate={() => void handleGenerate()}
        />

        {running && (
          <div className="mt-4">
            <JobProgressBar progress={jobProgress} label={statusLabel(jobStatus ?? 'running')} />
          </div>
        )}
        {generateError && (
          <div className="mt-4">
            <ErrorBanner message={generateError} />
          </div>
        )}
        {!running && lastGenerated && (
          <div className="mt-4">
            <Badge variant="success">
              Generated “{lastGenerated.name}” · {lastGenerated.record_count} records
            </Badge>
          </div>
        )}
      </section>

      {reviewRecord && (
        <RecordReviewModal
          record={reviewRecord}
          submitting={reviewSubmitting}
          errorMessage={reviewError}
          onClose={() => {
            setReviewRecord(null);
            setReviewError(null);
          }}
          onSubmit={handleReviewSubmit}
        />
      )}
    </div>
  );
}

function shortDescription(manifest: DatasetManifest): string {
  if (manifest.description) return manifest.description;
  return `${manifest.record_count} record${manifest.record_count === 1 ? '' : 's'} from ${manifest.source_path}`;
}
