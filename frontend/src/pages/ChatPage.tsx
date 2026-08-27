import axios from 'axios';
import { FormEvent, useCallback, useEffect, useState } from 'react';
import { ClipboardCheck, Loader2, Route, Send, ShieldAlert } from 'lucide-react';
import { ErrorBanner } from '../components/ErrorBanner';
import { PageHeader } from '../components/PageHeader';
import { StatCard } from '../components/StatCard';
import { evaluateResponse, fetchModels, routePrompt, sendChat } from '../services/api';
import type { ChatResponse, EvaluateResponse, ModelMetadata, RoutingDecision } from '../types';

const AUTO_MODEL = 'auto';

export function ChatPage() {
  const [models, setModels] = useState<ModelMetadata[]>([]);
  const [selectedModel, setSelectedModel] = useState(AUTO_MODEL);
  const [prompt, setPrompt] = useState('');
  const [qualityFloor, setQualityFloor] = useState<number | ''>('');
  const [response, setResponse] = useState<ChatResponse | null>(null);
  const [evaluation, setEvaluation] = useState<EvaluateResponse | null>(null);
  const [previewRouting, setPreviewRouting] = useState<RoutingDecision | null>(null);
  const [loading, setLoading] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [evaluating, setEvaluating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadModels = useCallback(async () => {
    try {
      const data = await fetchModels(true);
      setModels(data);
    } catch {
      setError('Failed to load models. Ensure the backend is running.');
    }
  }, []);

  useEffect(() => {
    loadModels();
  }, [loadModels]);

  const handlePreviewRoute = async () => {
    if (!prompt.trim()) return;
    setPreviewLoading(true);
    setError(null);
    try {
      const config = qualityFloor !== '' ? { quality_floor: qualityFloor } : undefined;
      const routing = await routePrompt(prompt.trim(), config);
      setPreviewRouting(routing);
    } catch (err: unknown) {
      if (axios.isAxiosError(err)) {
        const detail = err.response?.data?.detail;
        setError(typeof detail === 'string' ? detail : 'Routing preview failed.');
      } else {
        setError('Routing preview failed.');
      }
    } finally {
      setPreviewLoading(false);
    }
  };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!prompt.trim()) return;

    setLoading(true);
    setError(null);
    setResponse(null);
    setEvaluation(null);

    try {
      const result = await sendChat({
        model: selectedModel,
        messages: [{ role: 'user', content: prompt.trim() }],
        quality_floor: qualityFloor !== '' ? qualityFloor : undefined,
      });
      setResponse(result);
      setPreviewRouting(result.routing);
    } catch (err: unknown) {
      if (axios.isAxiosError(err)) {
        const detail = err.response?.data?.detail;
        setError(typeof detail === 'string' ? detail : 'Chat request failed.');
      } else {
        setError('Chat request failed.');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleEvaluate = async () => {
    if (!response || !prompt.trim()) return;
    setEvaluating(true);
    try {
      const result = await evaluateResponse(prompt.trim(), response.content);
      setEvaluation(result);
    } catch {
      setError('Evaluation failed.');
    } finally {
      setEvaluating(false);
    }
  };

  const routing = response?.routing ?? previewRouting;
  const isAuto = selectedModel === AUTO_MODEL;

  return (
    <div>
      <PageHeader
        title="Chat"
        description="Adaptive model routing analyzes your prompt and selects the best cost/latency trade-off that meets the quality floor."
      />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <form onSubmit={handleSubmit} className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
            <div className="mb-4 grid grid-cols-1 gap-4 md:grid-cols-2">
              <label className="block text-sm text-slate-400">
                Model
                <select
                  value={selectedModel}
                  onChange={(e) => setSelectedModel(e.target.value)}
                  className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
                >
                  <option value={AUTO_MODEL}>Auto (Adaptive Router)</option>
                  {models.map((model) => (
                    <option key={model.id} value={model.id}>
                      {model.name} ({model.tier}) — {model.provider}
                    </option>
                  ))}
                </select>
              </label>
              {isAuto && (
                <label className="block text-sm text-slate-400">
                  Quality Floor (optional)
                  <input
                    type="number"
                    min={0.5}
                    max={1}
                    step={0.05}
                    value={qualityFloor}
                    onChange={(e) => setQualityFloor(e.target.value === '' ? '' : Number(e.target.value))}
                    placeholder="Use server default"
                    className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
                  />
                </label>
              )}
            </div>

            <label className="mb-2 block text-sm text-slate-400">Your prompt</label>
            <textarea
              value={prompt}
              onChange={(e) => {
                setPrompt(e.target.value);
                setPreviewRouting(null);
              }}
              rows={5}
              placeholder="Ask a question, paste code to debug, or request analysis..."
              className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white placeholder:text-slate-600"
            />

            {error && <ErrorBanner message={error} />}

            <div className="mt-4 flex flex-wrap gap-3">
              <button
                type="submit"
                disabled={loading || !prompt.trim()}
                className="flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
              >
                {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                Send
              </button>
              {isAuto && (
                <button
                  type="button"
                  onClick={handlePreviewRoute}
                  disabled={previewLoading || !prompt.trim()}
                  className="flex items-center gap-2 rounded-lg border border-slate-700 px-4 py-2 text-sm text-slate-300 hover:bg-slate-800 disabled:opacity-50"
                >
                  {previewLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Route className="h-4 w-4" />}
                  Preview Routing
                </button>
              )}
              {response && (
                <button
                  type="button"
                  onClick={handleEvaluate}
                  disabled={evaluating}
                  className="flex items-center gap-2 rounded-lg border border-slate-700 px-4 py-2 text-sm text-slate-300 hover:bg-slate-800 disabled:opacity-50"
                >
                  {evaluating ? <Loader2 className="h-4 w-4 animate-spin" /> : <ClipboardCheck className="h-4 w-4" />}
                  Evaluate Response
                </button>
              )}
            </div>
          </form>

          {response && (
            <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-5">
              <div className="flex items-center justify-between gap-3">
                <h3 className="text-sm font-medium text-slate-400">Response</h3>
                {response.fallback?.used && (
                  <span className="inline-flex items-center gap-1 rounded-full border border-amber-500/30 bg-amber-500/10 px-2 py-1 text-xs text-amber-200">
                    <ShieldAlert className="h-3 w-3" />
                    Fallback used
                  </span>
                )}
              </div>
              <p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed text-slate-200">
                {response.content}
              </p>
              {response.fallback?.used && (
                <div className="mt-4 rounded-lg border border-slate-800 bg-slate-950/70 p-3 text-xs text-slate-400">
                  <p>
                    Escalated from <span className="text-white">{response.fallback.original_model}</span> to{' '}
                    <span className="text-white">{response.fallback.final_model}</span>
                    {response.fallback.escalation_reason
                      ? ` (${response.fallback.escalation_reason.replace(/_/g, ' ')})`
                      : ''}
                  </p>
                  <ul className="mt-2 space-y-1">
                    {response.fallback.attempts.map((attempt) => (
                      <li key={`${attempt.model_id}-${attempt.reason}`}>
                        {attempt.model_id}: {attempt.success ? 'success' : `failed (${attempt.reason})`}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          {evaluation && (
            <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-5">
              <h3 className="text-sm font-medium text-white">Judge Evaluation</h3>
              <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-3">
                {Object.entries(evaluation.scores)
                  .filter(([key]) => !['judge_provider', 'judge_reasoning'].includes(key))
                  .map(([key, value]) => (
                    <StatCard
                      key={key}
                      label={key.replace(/_/g, ' ')}
                      value={typeof value === 'number' ? `${(value * 100).toFixed(0)}%` : String(value)}
                    />
                  ))}
              </div>
              {evaluation.scores.judge_reasoning && (
                <p className="mt-3 text-xs text-slate-400">{evaluation.scores.judge_reasoning}</p>
              )}
            </div>
          )}
        </div>

        <div className="space-y-4">
          <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-5">
            <h3 className="text-sm font-medium text-white">Routing</h3>
            {routing ? (
              <dl className="mt-4 space-y-2 text-sm">
                <div className="flex justify-between">
                  <dt className="text-slate-400">Task</dt>
                  <dd className="capitalize text-white">{routing.task_type.replace(/_/g, ' ')}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-slate-400">Difficulty</dt>
                  <dd className="text-white">{(routing.difficulty * 100).toFixed(0)}%</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-slate-400">Selected</dt>
                  <dd className="text-white">{routing.selected_model}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-slate-400">Est. Quality</dt>
                  <dd className="text-white">{(routing.estimated_quality * 100).toFixed(0)}%</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-slate-400">Cost Saved</dt>
                  <dd className="text-emerald-300">${routing.cost_saved_vs_strong.toFixed(6)}</dd>
                </div>
              </dl>
            ) : (
              <p className="mt-3 text-sm text-slate-500">
                {isAuto ? 'Preview or send a message to see routing decisions.' : 'Select Auto to enable adaptive routing.'}
              </p>
            )}
          </div>

          {routing && routing.tier_qualities.length > 0 && (
            <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-5">
              <h3 className="text-sm font-medium text-white">Tier Comparison</h3>
              <div className="mt-3 space-y-2">
                {routing.tier_qualities.map((tier) => (
                  <div key={tier.tier} className="rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-2 text-xs">
                    <div className="flex justify-between capitalize text-slate-300">
                      <span>{tier.tier}</span>
                      <span className={tier.meets_quality_floor ? 'text-emerald-300' : 'text-amber-300'}>
                        {tier.meets_quality_floor ? 'meets floor' : 'below floor'}
                      </span>
                    </div>
                    <div className="mt-1 flex justify-between text-slate-500">
                      <span>Quality {(tier.expected_quality * 100).toFixed(0)}%</span>
                      <span>${tier.estimated_cost.toFixed(6)}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {routing && Object.keys(routing.features).length > 0 && (
            <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-5">
              <h3 className="text-sm font-medium text-white">Prompt Features</h3>
              <div className="mt-3 flex flex-wrap gap-2">
                {Object.entries(routing.features).map(([key, value]) => (
                  <span
                    key={key}
                    className="rounded-full border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-slate-400"
                  >
                    {key}: {String(value)}
                  </span>
                ))}
              </div>
            </div>
          )}

          {routing && (
            <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-5">
              <h3 className="text-sm font-medium text-white">Explanation</h3>
              <ul className="mt-3 space-y-2 text-sm text-slate-300">
                {routing.explanation.map((line: string) => (
                  <li key={line} className="flex gap-2">
                    <span className="text-brand-400">•</span>
                    <span>{line}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {response && (
            <StatCard
              label="Actual Cost"
              value={`$${response.cost.total_cost.toFixed(6)}`}
              subtext={`${response.model} · ${response.latency_ms.toFixed(0)} ms · ${response.usage.total_tokens} tokens`}
            />
          )}
        </div>
      </div>
    </div>
  );
}
