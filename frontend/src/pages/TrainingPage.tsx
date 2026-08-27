import { Link } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { Loader2, MessageSquare, Play } from 'lucide-react';
import { ErrorBanner } from '../components/ErrorBanner';
import { JobProgressBar } from '../components/JobProgressBar';
import { PageHeader } from '../components/PageHeader';
import { StatCard } from '../components/StatCard';
import {
  fetchDatasets,
  fetchTrainedModels,
  fetchTrainingStatus,
  startTraining,
} from '../services/api';
import type { DatasetManifest, TrainedModelInfo } from '../types';

export function TrainingPage() {
  const [datasets, setDatasets] = useState<DatasetManifest[]>([]);
  const [models, setModels] = useState<TrainedModelInfo[]>([]);
  const [datasetId, setDatasetId] = useState('');
  const [routerType, setRouterType] = useState<'tfidf' | 'embedding' | 'bert'>('tfidf');
  const [threshold, setThreshold] = useState(0.6);
  const [loading, setLoading] = useState(false);
  const [jobProgress, setJobProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<TrainedModelInfo | null>(null);

  useEffect(() => {
    fetchDatasets().then((data) => {
      setDatasets(data);
      if (data.length > 0) setDatasetId(data[0].id);
    });
    fetchTrainedModels().then(setModels).catch(() => setModels([]));
  }, [result]);

  const handleTrain = async () => {
    if (!datasetId) return;
    setLoading(true);
    setError(null);
    setResult(null);
    setJobProgress(0);
    try {
      const job = await startTraining({
        dataset_id: datasetId,
        router_type: routerType,
        routing_threshold: threshold,
      });

      const poll = async () => {
        const status = await fetchTrainingStatus(job.job_id);
        setJobProgress(status.progress);
        if (status.status === 'completed' && status.result) {
          setResult(status.result);
          setLoading(false);
        } else if (status.status === 'failed') {
          setError(status.error ?? 'Training failed');
          setLoading(false);
        } else {
          setTimeout(poll, 2000);
        }
      };
      poll();
    } catch {
      setError('Failed to start training.');
      setLoading(false);
    }
  };

  return (
    <div>
      <PageHeader
        title="Training"
        description="Train TF-IDF, embedding, and BERT-style routers from preference datasets."
        action={
          <Link
            to="/chat"
            className="flex items-center gap-2 rounded-lg border border-slate-700 px-4 py-2 text-sm text-slate-300 hover:bg-slate-800"
          >
            <MessageSquare className="h-4 w-4" />
            Test in Chat
          </Link>
        }
      />

      <div className="mb-6 grid grid-cols-1 gap-4 rounded-xl border border-slate-800 bg-slate-900/60 p-5 md:grid-cols-4">
        <label className="text-sm text-slate-400">
          Dataset
          <select
            value={datasetId}
            onChange={(e) => setDatasetId(e.target.value)}
            className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-white"
          >
            {datasets.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name} ({d.record_count})
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm text-slate-400">
          Router Type
          <select
            value={routerType}
            onChange={(e) => setRouterType(e.target.value as 'tfidf' | 'embedding' | 'bert')}
            className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-white"
          >
            <option value="tfidf">TF-IDF + Logistic Regression</option>
            <option value="embedding">Embedding + Classifier</option>
            <option value="bert">BERT-style MLP</option>
          </select>
        </label>
        <label className="text-sm text-slate-400">
          Routing Threshold
          <input
            type="number"
            min={0.1}
            max={1}
            step={0.05}
            value={threshold}
            onChange={(e) => setThreshold(Number(e.target.value))}
            className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-white"
          />
        </label>
        <div className="flex items-end">
          <button
            onClick={handleTrain}
            disabled={loading || !datasetId}
            className="flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
          >
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
            Start Training
          </button>
        </div>
      </div>

      {loading && <JobProgressBar progress={jobProgress} label="Training router model..." />}
      {error && <ErrorBanner message={error} />}

      {result && (
        <>
          <div className="mb-6 grid grid-cols-1 gap-4 md:grid-cols-4">
            <StatCard label="Router" value={result.router_type.toUpperCase()} />
            <StatCard label="Train Accuracy" value={`${(result.metrics.train_accuracy * 100).toFixed(1)}%`} />
            <StatCard label="Validation Accuracy" value={`${(result.metrics.validation_accuracy * 100).toFixed(1)}%`} />
            <StatCard label="Test Accuracy" value={`${(result.metrics.test_accuracy * 100).toFixed(1)}%`} />
            <StatCard label="Precision" value={result.metrics.precision.toFixed(3)} />
            <StatCard label="Recall" value={result.metrics.recall.toFixed(3)} />
            <StatCard label="F1 Score" value={result.metrics.f1.toFixed(3)} />
            <StatCard label="Samples" value={result.samples} subtext={`Threshold ${result.threshold}`} />
          </div>

          <div className="mb-6 rounded-xl border border-slate-800 bg-slate-900/60 p-5">
            <h3 className="text-sm font-medium text-white">Confusion Matrix (Test)</h3>
            <div className="mt-4 grid grid-cols-2 gap-4 md:grid-cols-4">
              <StatCard label="True Negative" value={result.metrics.confusion_matrix.true_negative} />
              <StatCard label="False Positive" value={result.metrics.confusion_matrix.false_positive} />
              <StatCard label="False Negative" value={result.metrics.confusion_matrix.false_negative} />
              <StatCard label="True Positive" value={result.metrics.confusion_matrix.true_positive} />
            </div>
            <p className="mt-4 text-sm text-slate-400">
              Set <code className="text-brand-100">ROUTER_TYPE={result.router_type}</code> in `.env` and restart the backend.
            </p>
          </div>
        </>
      )}

      {models.length > 0 && (
        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-5">
          <h3 className="text-sm font-medium text-white">Trained Models</h3>
          <div className="mt-3 overflow-hidden rounded-lg border border-slate-800">
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-950/80 text-slate-400">
                <tr>
                  <th className="px-4 py-2">Type</th>
                  <th className="px-4 py-2">Test Acc</th>
                  <th className="px-4 py-2">F1</th>
                  <th className="px-4 py-2">Threshold</th>
                  <th className="px-4 py-2">Created</th>
                </tr>
              </thead>
              <tbody>
                {models.slice(0, 10).map((model) => (
                  <tr key={model.id} className="border-t border-slate-800 text-slate-300">
                    <td className="px-4 py-2 uppercase">{model.router_type}</td>
                    <td className="px-4 py-2">{(model.metrics.test_accuracy * 100).toFixed(1)}%</td>
                    <td className="px-4 py-2">{model.metrics.f1.toFixed(3)}</td>
                    <td className="px-4 py-2">{model.threshold}</td>
                    <td className="px-4 py-2">{new Date(model.created_at).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
