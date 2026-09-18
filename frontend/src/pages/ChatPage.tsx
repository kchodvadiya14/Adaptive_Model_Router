import { KeyboardEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ClipboardCheck, MessageSquare, RotateCcw, Route, Send } from 'lucide-react';
import { Badge } from '../components/Badge';
import { Button } from '../components/Button';
import { Card } from '../components/Card';
import { EmptyState } from '../components/EmptyState';
import { ErrorBanner } from '../components/ErrorBanner';
import { Input } from '../components/Input';
import { MarkdownContent } from '../components/MarkdownContent';
import { PageHeader } from '../components/PageHeader';
import { Select } from '../components/Select';
import { evaluateResponse, fetchModelHealth, fetchModels, routePrompt, sendChat } from '../services/api';
import type {
  ChatMessage,
  ChatRequest,
  ChatResponse,
  EvaluateResponse,
  ModelHealthStatus,
  ModelMetadata,
  RoutingDecision,
} from '../types';
import { formatCost, formatMs } from './models/format';
import { parseApiError } from './chat/apiError';
import { CAPABILITY_TOOL_STUB, EXAMPLE_PROMPTS } from './chat/examples';
import { RoutingPanel } from './chat/RoutingPanel';

const AUTO_MODEL = 'auto';

interface ConversationTurn {
  id: string;
  prompt: string;
  response: ChatResponse | null;
  error: string | null;
  isTimeout: boolean;
}

function optionalNumber(value: string): number | undefined {
  const trimmed = value.trim();
  if (!trimmed) return undefined;
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? parsed : undefined;
}

function newSessionId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `session-${Date.now()}`;
}

export function ChatPage() {
  const [models, setModels] = useState<ModelMetadata[]>([]);
  const [healthByModel, setHealthByModel] = useState<Record<string, ModelHealthStatus>>({});
  const [selectedModel, setSelectedModel] = useState(AUTO_MODEL);
  const [preferredModel, setPreferredModel] = useState('');
  const [prompt, setPrompt] = useState('');
  const [qualityFloor, setQualityFloor] = useState('');
  const [maxCost, setMaxCost] = useState('');
  const [maxLatency, setMaxLatency] = useState('');
  const [timeoutMs, setTimeoutMs] = useState('');
  const [requiresVision, setRequiresVision] = useState(false);
  const [requiresTools, setRequiresTools] = useState(false);
  const [sentCapabilities, setSentCapabilities] = useState<string[]>([]);
  const [sessionId, setSessionId] = useState(newSessionId);
  const [turns, setTurns] = useState<ConversationTurn[]>([]);
  const [evaluation, setEvaluation] = useState<EvaluateResponse | null>(null);
  const [previewRouting, setPreviewRouting] = useState<RoutingDecision | null>(null);
  const [loading, setLoading] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [evaluating, setEvaluating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [errorIsTimeout, setErrorIsTimeout] = useState(false);
  const transcriptRef = useRef<HTMLDivElement>(null);

  const isAuto = selectedModel === AUTO_MODEL;
  const lastTurn = turns[turns.length - 1] ?? null;
  const lastResponse = lastTurn?.response ?? null;
  const routing = lastResponse?.routing ?? previewRouting;
  const previewOnly = Boolean(previewRouting) && !lastResponse?.routing;

  const selectedModelMeta = useMemo(() => {
    const id = lastResponse?.model ?? routing?.selected_model;
    return models.find((model) => model.id === id);
  }, [lastResponse?.model, models, routing?.selected_model]);

  const currentCapabilities = useMemo(() => {
    const caps: string[] = [];
    if (requiresVision) caps.push('vision');
    if (requiresTools) caps.push('tools');
    return caps;
  }, [requiresTools, requiresVision]);

  const loadCatalog = useCallback(async () => {
    try {
      const [modelList, healthList] = await Promise.all([
        fetchModels(true),
        fetchModelHealth().catch(() => [] as ModelHealthStatus[]),
      ]);
      setModels(modelList);
      setHealthByModel(Object.fromEntries(healthList.map((item) => [item.model_id, item])));
    } catch {
      setError('Failed to load models. Ensure the backend is running.');
      setErrorIsTimeout(false);
    }
  }, []);

  useEffect(() => {
    loadCatalog();
  }, [loadCatalog]);

  useEffect(() => {
    const node = transcriptRef.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [turns, loading]);

  const buildRequest = (content: string): ChatRequest => {
    const messages: ChatMessage[] = [{ role: 'user', content, has_image: requiresVision || undefined }];
    const timeout = optionalNumber(timeoutMs);
    return {
      model: selectedModel,
      messages,
      quality_floor: isAuto ? optionalNumber(qualityFloor) : undefined,
      preferred_model: isAuto && preferredModel ? preferredModel : undefined,
      max_cost: optionalNumber(maxCost),
      max_latency_ms: optionalNumber(maxLatency),
      timeout_ms: timeout !== undefined ? Math.round(timeout) : undefined,
      tools: requiresTools ? CAPABILITY_TOOL_STUB : undefined,
      session_id: sessionId,
    };
  };

  const handlePreviewRoute = async () => {
    if (!prompt.trim() || !isAuto) return;
    setPreviewLoading(true);
    setError(null);
    setErrorIsTimeout(false);
    setSentCapabilities(currentCapabilities);
    try {
      const floor = optionalNumber(qualityFloor);
      const routingDecision = await routePrompt(
        prompt.trim(),
        floor !== undefined ? { quality_floor: floor } : undefined,
        {
          preferred_model: preferredModel || undefined,
          max_cost: optionalNumber(maxCost),
          max_latency_ms: optionalNumber(maxLatency),
        },
      );
      setPreviewRouting(routingDecision);
    } catch (err: unknown) {
      const parsed = parseApiError(err, 'Routing preview failed.');
      setError(parsed.message);
      setErrorIsTimeout(parsed.isTimeout);
    } finally {
      setPreviewLoading(false);
    }
  };

  const handleSend = async () => {
    const content = prompt.trim();
    if (!content || loading) return;

    setLoading(true);
    setError(null);
    setErrorIsTimeout(false);
    setEvaluation(null);
    setPreviewRouting(null);
    setSentCapabilities(currentCapabilities);

    const turnId = `${Date.now()}`;
    setTurns((current) => [...current, { id: turnId, prompt: content, response: null, error: null, isTimeout: false }]);
    setPrompt('');

    try {
      const result = await sendChat(buildRequest(content));
      setTurns((current) =>
        current.map((turn) => (turn.id === turnId ? { ...turn, response: result } : turn)),
      );
    } catch (err: unknown) {
      const parsed = parseApiError(err, 'Chat request failed.');
      setError(parsed.message);
      setErrorIsTimeout(parsed.isTimeout);
      setTurns((current) =>
        current.map((turn) =>
          turn.id === turnId ? { ...turn, error: parsed.message, isTimeout: parsed.isTimeout } : turn,
        ),
      );
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      void handleSend();
    }
  };

  const handleEvaluate = async () => {
    if (!lastResponse || !lastTurn?.prompt) return;
    setEvaluating(true);
    try {
      const result = await evaluateResponse(lastTurn.prompt, lastResponse.content);
      setEvaluation(result);
    } catch (err: unknown) {
      const parsed = parseApiError(err, 'Evaluation failed.');
      setError(parsed.message);
      setErrorIsTimeout(parsed.isTimeout);
    } finally {
      setEvaluating(false);
    }
  };

  const handleNewConversation = () => {
    setTurns([]);
    setPrompt('');
    setEvaluation(null);
    setPreviewRouting(null);
    setError(null);
    setErrorIsTimeout(false);
    setSessionId(newSessionId());
    setSentCapabilities([]);
  };

  return (
    <div>
      <PageHeader
        title="Gateway Playground"
        description="Send a prompt through the LLM gateway: routing decides the model, then you see the response and the explanation."
        action={
          <Button variant="secondary" onClick={handleNewConversation} disabled={loading}>
            <RotateCcw className="h-4 w-4" />
            New conversation
          </Button>
        }
      />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <Card>
            <div className="mb-4 grid grid-cols-1 gap-4 md:grid-cols-2">
              <label className="block text-sm text-ink-secondary">
                Model
                <Select
                  className="mt-2"
                  value={selectedModel}
                  onChange={(event) => setSelectedModel(event.target.value)}
                >
                  <option value={AUTO_MODEL}>Auto (adaptive router)</option>
                  {models.map((model) => (
                    <option key={model.id} value={model.id}>
                      {model.name} ({model.tier}) — {model.provider}
                    </option>
                  ))}
                </Select>
              </label>
              {isAuto && (
                <label className="block text-sm text-ink-secondary">
                  Preferred model
                  <Select
                    className="mt-2"
                    value={preferredModel}
                    onChange={(event) => setPreferredModel(event.target.value)}
                  >
                    <option value="">None — let the router choose</option>
                    {models.map((model) => (
                      <option key={model.id} value={model.id}>
                        {model.name}
                      </option>
                    ))}
                  </Select>
                </label>
              )}
              {isAuto && (
                <label className="block text-sm text-ink-secondary">
                  Quality floor
                  <Input
                    className="mt-2"
                    type="number"
                    min={0}
                    max={1}
                    step={0.05}
                    value={qualityFloor}
                    onChange={(event) => setQualityFloor(event.target.value)}
                    placeholder="Server default"
                  />
                </label>
              )}
              <label className="block text-sm text-ink-secondary">
                Max cost (USD)
                <Input
                  className="mt-2"
                  type="number"
                  min={0}
                  step="0.000001"
                  value={maxCost}
                  onChange={(event) => setMaxCost(event.target.value)}
                  placeholder="No cap"
                />
              </label>
              <label className="block text-sm text-ink-secondary">
                Max latency (ms)
                <Input
                  className="mt-2"
                  type="number"
                  min={0}
                  step={10}
                  value={maxLatency}
                  onChange={(event) => setMaxLatency(event.target.value)}
                  placeholder="No cap"
                />
              </label>
              <label className="block text-sm text-ink-secondary">
                Timeout (ms)
                <Input
                  className="mt-2"
                  type="number"
                  min={1}
                  max={600000}
                  step={100}
                  value={timeoutMs}
                  onChange={(event) => setTimeoutMs(event.target.value)}
                  placeholder="No request deadline"
                />
              </label>
            </div>

            <div className="mb-4 flex flex-wrap gap-4 text-sm text-ink-secondary">
              <label className="inline-flex items-center gap-2">
                <input
                  type="checkbox"
                  className="h-4 w-4 rounded border-line bg-surface-1 text-brand-600"
                  checked={requiresVision}
                  onChange={(event) => setRequiresVision(event.target.checked)}
                />
                Requires vision
              </label>
              <label className="inline-flex items-center gap-2">
                <input
                  type="checkbox"
                  className="h-4 w-4 rounded border-line bg-surface-1 text-brand-600"
                  checked={requiresTools}
                  onChange={(event) => setRequiresTools(event.target.checked)}
                />
                Requires tools
              </label>
            </div>

            <p className="mb-2 text-xs text-ink-muted">Example prompts</p>
            <div className="mb-4 flex flex-wrap gap-2">
              {EXAMPLE_PROMPTS.map((example) => (
                <button
                  key={example.id}
                  type="button"
                  title={example.description}
                  onClick={() => {
                    setPrompt(example.prompt);
                    setPreviewRouting(null);
                  }}
                  className="rounded-full border border-line bg-surface-1 px-3 py-1 text-xs text-ink-secondary hover:border-brand-500/40 hover:text-ink-primary"
                >
                  {example.label}
                </button>
              ))}
            </div>

            <label className="mb-2 block text-sm text-ink-secondary">Prompt</label>
            <textarea
              value={prompt}
              onChange={(event) => {
                setPrompt(event.target.value);
                setPreviewRouting(null);
              }}
              onKeyDown={handleKeyDown}
              rows={6}
              disabled={loading}
              placeholder="Ask a question, paste code, or request analysis… Enter to send, Shift+Enter for a new line."
              className="w-full resize-y rounded-control border border-line bg-surface-1 px-3 py-2 text-sm text-ink-primary placeholder:text-ink-muted focus:outline-none focus:ring-2 focus:ring-brand-500/50 disabled:opacity-50"
            />

            {error && (
              <div className="mt-3">
                <ErrorBanner
                  message={errorIsTimeout ? `Timeout: ${error}` : error}
                  variant={errorIsTimeout ? 'warning' : 'error'}
                />
              </div>
            )}

            <div className="mt-4 flex flex-wrap gap-3">
              <Button type="button" onClick={() => void handleSend()} loading={loading} disabled={!prompt.trim()}>
                {!loading && <Send className="h-4 w-4" />}
                Send
              </Button>
              {isAuto && (
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() => void handlePreviewRoute()}
                  loading={previewLoading}
                  disabled={!prompt.trim() || loading}
                >
                  {!previewLoading && <Route className="h-4 w-4" />}
                  Preview routing
                </Button>
              )}
              {lastResponse && (
                <Button type="button" variant="ghost" onClick={() => void handleEvaluate()} loading={evaluating}>
                  {!evaluating && <ClipboardCheck className="h-4 w-4" />}
                  Evaluate response
                </Button>
              )}
            </div>
          </Card>

          <Card padding="none" className="overflow-hidden">
            <div className="flex items-center justify-between border-b border-line px-5 py-3">
              <h3 className="text-sm font-medium text-ink-primary">Conversation</h3>
              {lastResponse && (
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant={lastResponse.tier}>{lastResponse.tier}</Badge>
                  <span className="text-xs text-ink-muted">
                    {lastResponse.model_name} · {formatMs(lastResponse.latency_ms)} · {formatCost(lastResponse.cost.total_cost)}
                  </span>
                </div>
              )}
            </div>
            <div ref={transcriptRef} className="max-h-[32rem] space-y-4 overflow-y-auto px-5 py-4">
              {turns.length === 0 && !loading && (
                <EmptyState
                  icon={MessageSquare}
                  title="No messages yet"
                  description="Choose an example or write a prompt, then send it through the gateway."
                />
              )}
              {turns.map((turn) => (
                <div key={turn.id} className="space-y-3">
                  <div className="ml-8 rounded-xl border border-line bg-surface-3/70 px-4 py-3">
                    <p className="mb-1 text-[11px] font-medium uppercase tracking-wide text-ink-muted">You</p>
                    <p className="whitespace-pre-wrap text-sm leading-relaxed text-ink-primary">{turn.prompt}</p>
                  </div>
                  {turn.response && (
                    <div className="mr-8 rounded-xl border border-brand-500/20 bg-surface-1 px-4 py-3">
                      <p className="mb-1 text-[11px] font-medium uppercase tracking-wide text-brand-300">
                        {turn.response.model_name || turn.response.model}
                      </p>
                      <MarkdownContent content={turn.response.content} />
                    </div>
                  )}
                  {turn.error && (
                    <div className="mr-8">
                      <ErrorBanner
                        message={turn.isTimeout ? `Timeout: ${turn.error}` : turn.error}
                        variant={turn.isTimeout ? 'warning' : 'error'}
                      />
                    </div>
                  )}
                </div>
              ))}
              {loading && (
                <div className="mr-8 animate-pulse rounded-xl border border-line bg-surface-1 px-4 py-3">
                  <div className="h-3 w-24 rounded bg-surface-3" />
                  <div className="mt-3 h-3 w-full rounded bg-surface-3" />
                  <div className="mt-2 h-3 w-2/3 rounded bg-surface-3" />
                </div>
              )}
            </div>
          </Card>

          {evaluation && (
            <Card>
              <h3 className="text-sm font-medium text-ink-primary">Judge evaluation</h3>
              <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-3">
                {Object.entries(evaluation.scores)
                  .filter(([key]) => !['judge_provider', 'judge_reasoning'].includes(key))
                  .map(([key, value]) => (
                    <div key={key} className="rounded-lg border border-line bg-surface-1 px-3 py-2">
                      <p className="text-xs capitalize text-ink-muted">{key.replace(/_/g, ' ')}</p>
                      <p className="mt-1 text-sm font-medium text-ink-primary">
                        {typeof value === 'number' ? `${(value * 100).toFixed(0)}%` : String(value)}
                      </p>
                    </div>
                  ))}
              </div>
              {evaluation.scores.judge_reasoning && (
                <p className="mt-3 text-xs text-ink-secondary">{evaluation.scores.judge_reasoning}</p>
              )}
            </Card>
          )}
        </div>

        <RoutingPanel
          routing={routing}
          response={lastResponse}
          selectedModelMeta={selectedModelMeta}
          selectedHealth={
            (selectedModelMeta && healthByModel[selectedModelMeta.id]) ||
            (routing ? healthByModel[routing.selected_model] : undefined) ||
            (lastResponse ? healthByModel[lastResponse.model] : undefined)
          }
          requestedCapabilities={lastResponse || previewRouting ? sentCapabilities : currentCapabilities}
          pinnedModel={!isAuto}
          previewOnly={previewOnly}
        />
      </div>
    </div>
  );
}
