import { useCallback, useEffect, useMemo, useState } from 'react';
import { Activity, Bot, History, Plus, RefreshCw, Search, ToggleLeft, ToggleRight } from 'lucide-react';
import { Badge } from '../components/Badge';
import { Button } from '../components/Button';
import { Card } from '../components/Card';
import { EmptyState } from '../components/EmptyState';
import { ErrorBanner } from '../components/ErrorBanner';
import { Input } from '../components/Input';
import { PageHeader } from '../components/PageHeader';
import { StatCard } from '../components/StatCard';
import { Table, TableContainer, TBody, Td, Th, THead, Tr } from '../components/Table';
import {
  createModel,
  disableModel,
  enableModel,
  fetchModelHealth,
  fetchModelPerformance,
  fetchModels,
  fetchRouterStatus,
  updateModel,
} from '../services/api';
import type {
  ModelCreateRequest,
  ModelHealthStatus,
  ModelMetadata,
  ModelPerformance,
  RouterStatusResponse,
} from '../types';
import { ModelDetailModal } from './models/ModelDetailModal';
import { ModelFormModal } from './models/ModelFormModal';
import {
  formatCountdown,
  formatMs,
  formatPercent,
  HEALTH_BADGE_VARIANT,
  HEALTH_LABEL,
} from './models/format';

const emptyForm: ModelCreateRequest = {
  id: '',
  name: '',
  provider: 'mock',
  type: 'local',
  tier: 'small',
  input_cost_per_1m_tokens: 0,
  output_cost_per_1m_tokens: 0,
  context_window: 32000,
  capabilities: ['general'],
  supports_vision: false,
  supports_tools: false,
  enabled: true,
  avg_latency_ms: 100,
  quality_score: 0.85,
};

function toFormValue(model: ModelMetadata): ModelCreateRequest {
  return {
    id: model.id,
    name: model.name,
    provider: model.provider,
    type: model.type,
    tier: model.tier,
    input_cost_per_1m_tokens: model.input_cost_per_1m_tokens,
    output_cost_per_1m_tokens: model.output_cost_per_1m_tokens,
    context_window: model.context_window,
    capabilities: model.capabilities,
    supports_vision: model.supports_vision,
    supports_tools: model.supports_tools,
    enabled: model.enabled,
    avg_latency_ms: model.avg_latency_ms,
    quality_score: model.quality_score,
  };
}

function SkeletonBar({ className = '' }: { className?: string }) {
  return <div className={`animate-pulse rounded bg-surface-3 ${className}`} />;
}

function SkeletonRow() {
  return (
    <Tr className="hover:bg-transparent">
      {Array.from({ length: 9 }).map((_, index) => (
        <Td key={index}>
          <SkeletonBar className="h-4 w-16" />
        </Td>
      ))}
    </Tr>
  );
}

export function ModelsPage() {
  const [models, setModels] = useState<ModelMetadata[]>([]);
  const [routerStatus, setRouterStatus] = useState<RouterStatusResponse | null>(null);
  const [healthList, setHealthList] = useState<ModelHealthStatus[]>([]);
  const [performanceList, setPerformanceList] = useState<ModelPerformance[]>([]);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [healthUnavailable, setHealthUnavailable] = useState(false);
  const [performanceUnavailable, setPerformanceUnavailable] = useState(false);

  const [search, setSearch] = useState('');

  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [formInitialValue, setFormInitialValue] = useState<ModelCreateRequest>(emptyForm);
  const [formSubmitting, setFormSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const [detailModelId, setDetailModelId] = useState<string | null>(null);
  const [togglingId, setTogglingId] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    const [modelsResult, statusResult, healthResult, performanceResult] = await Promise.allSettled([
      fetchModels(),
      fetchRouterStatus(),
      fetchModelHealth(),
      fetchModelPerformance(),
    ]);

    if (modelsResult.status === 'fulfilled') {
      setModels(modelsResult.value);
    } else {
      setError('Failed to load the model registry. Ensure the backend is running on port 8000.');
      setModels([]);
    }

    setRouterStatus(statusResult.status === 'fulfilled' ? statusResult.value : null);

    setHealthUnavailable(healthResult.status !== 'fulfilled');
    setHealthList(healthResult.status === 'fulfilled' ? healthResult.value : []);

    setPerformanceUnavailable(performanceResult.status !== 'fulfilled');
    setPerformanceList(performanceResult.status === 'fulfilled' ? performanceResult.value.models : []);

    setLoading(false);
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const healthByModelId = useMemo(() => {
    const map = new Map<string, ModelHealthStatus>();
    healthList.forEach((entry) => map.set(entry.model_id, entry));
    return map;
  }, [healthList]);

  const performanceByModelId = useMemo(() => {
    const map = new Map<string, ModelPerformance>();
    performanceList.forEach((entry) => map.set(entry.model_id, entry));
    return map;
  }, [performanceList]);

  const filteredModels = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return models;
    return models.filter(
      (model) =>
        model.name.toLowerCase().includes(query) ||
        model.id.toLowerCase().includes(query) ||
        model.provider.toLowerCase().includes(query),
    );
  }, [models, search]);

  const openCircuits = healthUnavailable ? null : healthList.filter((entry) => entry.state === 'open').length;

  const toggleModel = async (model: ModelMetadata) => {
    setTogglingId(model.id);
    setError(null);
    try {
      const updated = model.enabled ? await disableModel(model.id) : await enableModel(model.id);
      setModels((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
      fetchRouterStatus()
        .then(setRouterStatus)
        .catch(() => undefined);
    } catch {
      setError(`Failed to ${model.enabled ? 'disable' : 'enable'} "${model.name}".`);
    } finally {
      setTogglingId(null);
    }
  };

  const openCreate = () => {
    setEditingId(null);
    setFormInitialValue(emptyForm);
    setFormError(null);
    setShowForm(true);
  };

  const openEdit = (model: ModelMetadata) => {
    setEditingId(model.id);
    setFormInitialValue(toFormValue(model));
    setFormError(null);
    setShowForm(true);
  };

  const handleFormSubmit = async (form: ModelCreateRequest) => {
    setFormSubmitting(true);
    setFormError(null);
    try {
      if (editingId) {
        const { id: _unusedId, ...updates } = form;
        void _unusedId;
        const updated = await updateModel(editingId, updates);
        setModels((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
      } else {
        const created = await createModel(form);
        setModels((prev) => [...prev, created]);
      }
      setShowForm(false);
    } catch {
      setFormError(
        editingId ? 'Failed to update this model.' : 'Failed to create model — the ID may already be in use.',
      );
    } finally {
      setFormSubmitting(false);
    }
  };

  const detailModel = detailModelId ? models.find((model) => model.id === detailModelId) ?? null : null;

  return (
    <div>
      <PageHeader
        title="Model Registry"
        description="Configure providers, tiers and capabilities, and monitor live circuit health and historical performance."
        action={
          <div className="flex gap-2">
            <Button onClick={openCreate}>
              <Plus className="h-4 w-4" />
              Add Model
            </Button>
            <Button variant="secondary" onClick={loadData} disabled={loading}>
              <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
              Refresh
            </Button>
          </div>
        }
      />

      <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {loading ? (
          Array.from({ length: 4 }).map((_, index) => (
            <Card key={index}>
              <SkeletonBar className="h-4 w-24" />
              <SkeletonBar className="mt-3 h-7 w-14" />
            </Card>
          ))
        ) : (
          <>
            <StatCard label="Total Models" value={models.length} />
            <StatCard label="Enabled Models" value={models.filter((model) => model.enabled).length} />
            <StatCard
              label="Circuits Open"
              value={openCircuits ?? '—'}
              subtext={healthUnavailable ? 'Live health unavailable' : 'Temporarily unavailable models'}
            />
            <StatCard
              label="Quality Floor"
              value={routerStatus ? `${(routerStatus.quality_floor * 100).toFixed(0)}%` : '—'}
              subtext={routerStatus ? `Router: ${routerStatus.router_type}` : undefined}
            />
          </>
        )}
      </div>

      {error && <ErrorBanner message={error} />}
      {!error && healthUnavailable && !loading && (
        <ErrorBanner variant="warning" message="Live health data unavailable — showing registry data only." />
      )}
      {!error && performanceUnavailable && !loading && (
        <ErrorBanner variant="warning" message="Historical performance data unavailable." />
      )}

      {!loading && !error && models.length === 0 ? (
        <EmptyState
          icon={Bot}
          title="No models registered"
          description="Add your first model to make it available for routing."
        />
      ) : (
        <>
          {!loading && models.length > 0 && (
            <div className="mb-4 max-w-xs">
              <div className="relative">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-muted" />
                <Input
                  placeholder="Search by name, ID or provider…"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  className="pl-9"
                />
              </div>
            </div>
          )}

          <TableContainer>
            <Table className="min-w-[1280px]">
              <THead>
                <tr>
                  <th colSpan={6} className="border-b border-line px-4 pt-3 text-left text-[11px] font-semibold uppercase tracking-wide text-ink-muted">
                    Registry
                  </th>
                  <th colSpan={3} className="border-b border-line border-l border-line-strong bg-surface-3/30 px-4 pt-3 text-left text-[11px] font-semibold uppercase tracking-wide text-ink-muted">
                    <span className="inline-flex items-center gap-1.5">
                      <Activity className="h-3 w-3" /> Live Health
                    </span>
                  </th>
                  <th colSpan={5} className="border-b border-line border-l border-line-strong bg-surface-3/30 px-4 pt-3 text-left text-[11px] font-semibold uppercase tracking-wide text-ink-muted">
                    <span className="inline-flex items-center gap-1.5">
                      <History className="h-3 w-3" /> Historical Performance
                    </span>
                  </th>
                  <th className="border-b border-line" />
                </tr>
                <Tr className="hover:bg-transparent">
                  <Th>Model</Th>
                  <Th>Provider</Th>
                  <Th>Tier</Th>
                  <Th>Context</Th>
                  <Th>Capabilities</Th>
                  <Th>Status</Th>
                  <Th className="border-l border-line-strong bg-surface-3/30">State</Th>
                  <Th className="bg-surface-3/30">Failures</Th>
                  <Th className="bg-surface-3/30">Cooldown</Th>
                  <Th className="border-l border-line-strong bg-surface-3/30">Requests</Th>
                  <Th className="bg-surface-3/30">Success</Th>
                  <Th className="bg-surface-3/30">Avg. latency</Th>
                  <Th className="bg-surface-3/30">Avg. quality</Th>
                  <Th className="bg-surface-3/30">Fallback</Th>
                  <Th>Actions</Th>
                </Tr>
              </THead>
              <TBody>
                {loading ? (
                  Array.from({ length: 5 }).map((_, index) => <SkeletonRow key={index} />)
                ) : filteredModels.length === 0 ? (
                  <tr>
                    <td colSpan={15} className="px-4 py-10 text-center text-sm text-ink-muted">
                      No models match “{search}”.
                    </td>
                  </tr>
                ) : (
                  filteredModels.map((model) => {
                    const health = healthByModelId.get(model.id);
                    const performance = performanceByModelId.get(model.id);
                    return (
                      <Tr key={model.id}>
                        <Td>
                          <button
                            onClick={() => setDetailModelId(model.id)}
                            className="text-left font-medium text-ink-primary hover:text-brand-400 hover:underline"
                          >
                            {model.name}
                          </button>
                          <div className="font-mono text-xs text-ink-muted">{model.id}</div>
                        </Td>
                        <Td className="capitalize text-ink-secondary">{model.provider}</Td>
                        <Td>
                          <Badge variant={model.tier}>{model.tier}</Badge>
                        </Td>
                        <Td className="whitespace-nowrap text-ink-secondary">
                          {model.context_window.toLocaleString()} tok
                        </Td>
                        <Td>
                          <div className="flex gap-1">
                            <Badge variant={model.supports_vision ? 'info' : 'neutral'}>Vision</Badge>
                            <Badge variant={model.supports_tools ? 'info' : 'neutral'}>Tools</Badge>
                          </div>
                        </Td>
                        <Td>
                          <Badge variant={model.enabled ? 'success' : 'neutral'}>
                            {model.enabled ? 'Enabled' : 'Disabled'}
                          </Badge>
                        </Td>
                        <Td className="whitespace-nowrap border-l border-line-strong">
                          {healthUnavailable ? (
                            <span className="text-ink-muted">—</span>
                          ) : health ? (
                            <Badge variant={HEALTH_BADGE_VARIANT[health.state]}>{HEALTH_LABEL[health.state]}</Badge>
                          ) : (
                            <Badge variant="neutral">Unknown</Badge>
                          )}
                        </Td>
                        <Td className="text-ink-secondary">{healthUnavailable ? '—' : (health?.consecutive_failures ?? 0)}</Td>
                        <Td className="whitespace-nowrap text-ink-secondary">
                          {healthUnavailable || health?.state !== 'open'
                            ? '—'
                            : formatCountdown(health.cooldown_remaining_seconds)}
                        </Td>
                        <Td className="border-l border-line-strong text-ink-secondary">
                          {performanceUnavailable ? '—' : (performance?.request_count.toLocaleString() ?? 0)}
                        </Td>
                        <Td className="text-ink-secondary">
                          {performanceUnavailable ? '—' : performance ? formatPercent(performance.success_rate) : '—'}
                        </Td>
                        <Td className="whitespace-nowrap text-ink-secondary">
                          {performanceUnavailable ? '—' : performance ? formatMs(performance.average_latency_ms) : '—'}
                        </Td>
                        <Td className="text-ink-secondary">
                          {performanceUnavailable
                            ? '—'
                            : performance
                              ? formatPercent(performance.average_quality_score)
                              : '—'}
                        </Td>
                        <Td className="text-ink-secondary">
                          {performanceUnavailable ? '—' : performance ? formatPercent(performance.fallback_rate) : '—'}
                        </Td>
                        <Td>
                          <div className="flex items-center gap-3 whitespace-nowrap">
                            <button
                              onClick={() => openEdit(model)}
                              className="text-xs font-medium text-brand-400 hover:text-brand-300"
                            >
                              Edit
                            </button>
                            <button
                              onClick={() => toggleModel(model)}
                              disabled={togglingId === model.id}
                              aria-label={model.enabled ? 'Disable model' : 'Enable model'}
                              className="text-ink-muted transition-colors hover:text-ink-primary disabled:opacity-50"
                            >
                              {model.enabled ? (
                                <ToggleRight className="h-5 w-5 text-success-400" />
                              ) : (
                                <ToggleLeft className="h-5 w-5" />
                              )}
                            </button>
                          </div>
                        </Td>
                      </Tr>
                    );
                  })
                )}
              </TBody>
            </Table>
          </TableContainer>
        </>
      )}

      {showForm && (
        <ModelFormModal
          key={editingId ?? 'create'}
          open={showForm}
          editingId={editingId}
          initialValue={formInitialValue}
          submitting={formSubmitting}
          errorMessage={formError}
          onClose={() => setShowForm(false)}
          onSubmit={handleFormSubmit}
        />
      )}

      <ModelDetailModal
        model={detailModel}
        allModels={models}
        health={detailModel ? healthByModelId.get(detailModel.id) : undefined}
        performance={detailModel ? performanceByModelId.get(detailModel.id) : undefined}
        healthUnavailable={healthUnavailable}
        performanceUnavailable={performanceUnavailable}
        onClose={() => setDetailModelId(null)}
      />
    </div>
  );
}
