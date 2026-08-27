import { FormEvent, useCallback, useEffect, useState } from 'react';
import { Database, Loader2, Play, X } from 'lucide-react';
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
import type { DatasetManifest, PreferenceRecord } from '../types';

const PAGE_SIZE = 10;

export function DatasetPage() {
  const [datasets, setDatasets] = useState<DatasetManifest[]>([]);
  const [selectedId, setSelectedId] = useState<string>('');
  const [records, setRecords] = useState<PreferenceRecord[]>([]);
  const [totalRecords, setTotalRecords] = useState(0);
  const [page, setPage] = useState(0);
  const [sourcePath, setSourcePath] = useState('data/benchmarks/sample_prompts.json');
  const [qualityFloor, setQualityFloor] = useState(0.9);
  const [maxPrompts, setMaxPrompts] = useState(8);
  const [loading, setLoading] = useState(false);
  const [jobProgress, setJobProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [selectedRecord, setSelectedRecord] = useState<PreferenceRecord | null>(null);
  const [humanForm, setHumanForm] = useState({
    small_score: 0.8,
    medium_score: 0.85,
    strong_score: 0.9,
    preferred_model: 'medium' as 'small' | 'medium' | 'strong',
    notes: '',
  });

  const loadDatasets = useCallback(async () => {
    try {
      const data = await fetchDatasets();
      setDatasets(data);
      if (!selectedId && data.length > 0) {
        setSelectedId(data[0].id);
      }
    } catch {
      setError('Failed to load datasets.');
    }
  }, [selectedId]);

  const loadRecords = useCallback(async () => {
    if (!selectedId) return;
    try {
      const data = await fetchDatasetRecords(selectedId, {
        offset: page * PAGE_SIZE,
        limit: PAGE_SIZE,
      });
      setRecords(data.records);
      setTotalRecords(data.total);
    } catch {
      setRecords([]);
    }
  }, [selectedId, page]);

  useEffect(() => {
    loadDatasets();
  }, [loadDatasets]);

  useEffect(() => {
    loadRecords();
  }, [loadRecords]);

  const handleGenerate = async () => {
    setLoading(true);
    setError(null);
    setJobProgress(0);
    try {
      const job = await startDatasetGeneration({
        source_path: sourcePath,
        name: `dataset_${Date.now()}`,
        quality_floor: qualityFloor,
        max_prompts: maxPrompts,
      });

      const poll = async () => {
        const status = await fetchDatasetGenerationStatus(job.job_id);
        setJobProgress(status.progress);
        if (status.status === 'completed' && status.manifest) {
          setSelectedId(status.manifest.id);
          setPage(0);
          await loadDatasets();
          setLoading(false);
        } else if (status.status === 'failed') {
          setError(status.error ?? 'Dataset generation failed');
          setLoading(false);
        } else {
          setTimeout(poll, 1500);
        }
      };
      poll();
    } catch {
      setError('Failed to start dataset generation.');
      setLoading(false);
    }
  };

  const handleHumanEval = async (event: FormEvent) => {
    event.preventDefault();
    if (!selectedId || !selectedRecord) return;
    try {
      await submitHumanEval(selectedId, {
        record_id: selectedRecord.id,
        small_score: humanForm.small_score,
        medium_score: humanForm.medium_score,
        strong_score: humanForm.strong_score,
        preferred_model: humanForm.preferred_model,
        notes: humanForm.notes || undefined,
      });
      setSelectedRecord(null);
      await loadRecords();
    } catch {
      setError('Failed to submit human evaluation.');
    }
  };

  const selected = datasets.find((d) => d.id === selectedId);
  const totalPages = Math.max(1, Math.ceil(totalRecords / PAGE_SIZE));

  return (
    <div>
      <PageHeader
        title="Dataset"
        description="Generate preference labels by collecting tier responses and scoring them with the judge. Override labels with human evaluation."
      />

      <div className="mb-6 grid grid-cols-1 gap-4 rounded-xl border border-slate-800 bg-slate-900/60 p-5 md:grid-cols-4">
        <label className="text-sm text-slate-400 md:col-span-2">
          Source Path
          <input
            value={sourcePath}
            onChange={(e) => setSourcePath(e.target.value)}
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
            max={50}
            value={maxPrompts}
            onChange={(e) => setMaxPrompts(Number(e.target.value))}
            className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-white"
          />
        </label>
        <div className="flex items-end md:col-span-2">
          <button
            onClick={handleGenerate}
            disabled={loading}
            className="flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
          >
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
            Generate Dataset
          </button>
        </div>
        <div className="flex items-end md:col-span-2">
          <StatCard label="Saved Datasets" value={datasets.length} subtext="JSONL in data/processed/datasets" />
        </div>
      </div>

      {loading && <JobProgressBar progress={jobProgress} label="Generating preference dataset..." />}
      {error && <ErrorBanner message={error} />}

      {datasets.length > 0 && (
        <div className="mb-4">
          <label className="mb-2 block text-sm text-slate-400">Select Dataset</label>
          <select
            value={selectedId}
            onChange={(e) => {
              setSelectedId(e.target.value);
              setPage(0);
            }}
            className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white md:w-96"
          >
            {datasets.map((dataset) => (
              <option key={dataset.id} value={dataset.id}>
                {dataset.name} · {dataset.record_count} records · floor {(dataset.quality_floor * 100).toFixed(0)}%
              </option>
            ))}
          </select>
        </div>
      )}

      {selected && (
        <div className="mb-4 grid grid-cols-1 gap-4 md:grid-cols-4">
          <StatCard label="Records" value={selected.record_count} />
          <StatCard label="Judge" value={selected.judge_provider} />
          <StatCard label="Source" value={selected.source_path.split('/').pop() ?? selected.source_path} />
          <StatCard label="Created" value={new Date(selected.created_at).toLocaleDateString()} />
        </div>
      )}

      {records.length > 0 ? (
        <>
          <div className="overflow-hidden rounded-xl border border-slate-800">
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-900/80 text-slate-400">
                <tr>
                  <th className="px-4 py-3">Prompt</th>
                  <th className="px-4 py-3">Task</th>
                  <th className="px-4 py-3">Scores</th>
                  <th className="px-4 py-3">Preferred</th>
                  <th className="px-4 py-3">Source</th>
                  <th className="px-4 py-3">Action</th>
                </tr>
              </thead>
              <tbody>
                {records.map((record) => (
                  <tr key={record.id} className="border-t border-slate-800 hover:bg-slate-900/40">
                    <td className="max-w-xs truncate px-4 py-3 text-slate-300">{record.prompt}</td>
                    <td className="px-4 py-3 capitalize text-slate-300">{record.task_type.replace(/_/g, ' ')}</td>
                    <td className="px-4 py-3 text-xs text-slate-400">
                      S {(record.small_score * 100).toFixed(0)}% · M {(record.medium_score * 100).toFixed(0)}% · St{' '}
                      {(record.strong_score * 100).toFixed(0)}%
                    </td>
                    <td className="px-4 py-3 capitalize text-brand-100">{record.preferred_model}</td>
                    <td className="px-4 py-3 capitalize text-slate-500">{record.evaluation_source}</td>
                    <td className="px-4 py-3">
                      <button
                        onClick={() => {
                          setSelectedRecord(record);
                          setHumanForm({
                            small_score: record.small_score,
                            medium_score: record.medium_score,
                            strong_score: record.strong_score,
                            preferred_model: record.preferred_model,
                            notes: record.human_notes ?? '',
                          });
                        }}
                        className="text-xs text-brand-300 hover:text-brand-200"
                      >
                        Review
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-4 flex items-center justify-between text-sm text-slate-400">
            <span>
              Page {page + 1} of {totalPages} · {totalRecords} records
            </span>
            <div className="flex gap-2">
              <button
                disabled={page === 0}
                onClick={() => setPage((p) => p - 1)}
                className="rounded border border-slate-700 px-3 py-1 disabled:opacity-40"
              >
                Previous
              </button>
              <button
                disabled={page + 1 >= totalPages}
                onClick={() => setPage((p) => p + 1)}
                className="rounded border border-slate-700 px-3 py-1 disabled:opacity-40"
              >
                Next
              </button>
            </div>
          </div>
        </>
      ) : (
        <EmptyState
          icon={Database}
          title="No preference records yet"
          description="Generate a dataset from sample prompts to begin building training data."
        />
      )}

      {selectedRecord && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-xl border border-slate-700 bg-slate-900 p-6">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-lg font-medium text-white">Record Review & Human Eval</h3>
              <button onClick={() => setSelectedRecord(null)} className="text-slate-400 hover:text-white">
                <X className="h-5 w-5" />
              </button>
            </div>
            <p className="mb-4 text-sm text-slate-300">{selectedRecord.prompt}</p>
            <div className="mb-4 space-y-3 text-xs text-slate-400">
              {selectedRecord.small_response && (
                <div className="rounded-lg border border-slate-800 p-3">
                  <p className="font-medium text-emerald-300">Small</p>
                  <p className="mt-1 whitespace-pre-wrap">{selectedRecord.small_response.slice(0, 400)}</p>
                </div>
              )}
              {selectedRecord.medium_response && (
                <div className="rounded-lg border border-slate-800 p-3">
                  <p className="font-medium text-amber-300">Medium</p>
                  <p className="mt-1 whitespace-pre-wrap">{selectedRecord.medium_response.slice(0, 400)}</p>
                </div>
              )}
              {selectedRecord.strong_response && (
                <div className="rounded-lg border border-slate-800 p-3">
                  <p className="font-medium text-rose-300">Strong</p>
                  <p className="mt-1 whitespace-pre-wrap">{selectedRecord.strong_response.slice(0, 400)}</p>
                </div>
              )}
            </div>
            <form onSubmit={handleHumanEval} className="space-y-3">
              <div className="grid grid-cols-3 gap-3">
                {(['small_score', 'medium_score', 'strong_score'] as const).map((key) => (
                  <label key={key} className="text-xs text-slate-400">
                    {key.replace('_score', '')}
                    <input
                      type="number"
                      min={0}
                      max={1}
                      step={0.05}
                      value={humanForm[key]}
                      onChange={(e) => setHumanForm({ ...humanForm, [key]: Number(e.target.value) })}
                      className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-2 py-1 text-white"
                    />
                  </label>
                ))}
              </div>
              <select
                value={humanForm.preferred_model}
                onChange={(e) =>
                  setHumanForm({ ...humanForm, preferred_model: e.target.value as 'small' | 'medium' | 'strong' })
                }
                className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
              >
                <option value="small">Prefer Small</option>
                <option value="medium">Prefer Medium</option>
                <option value="strong">Prefer Strong</option>
              </select>
              <textarea
                placeholder="Notes (optional)"
                value={humanForm.notes}
                onChange={(e) => setHumanForm({ ...humanForm, notes: e.target.value })}
                rows={2}
                className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
              />
              <button
                type="submit"
                className="w-full rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700"
              >
                Save Human Evaluation
              </button>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
