import { FormEvent, useCallback, useEffect, useState } from 'react';
import { Eye, Plus, RefreshCw, ToggleLeft, ToggleRight, X } from 'lucide-react';
import { ErrorBanner } from '../components/ErrorBanner';
import { PageHeader } from '../components/PageHeader';
import { StatCard } from '../components/StatCard';
import {
  createModel,
  disableModel,
  enableModel,
  fetchModel,
  fetchModels,
  fetchRouterStatus,
  updateModel,
} from '../services/api';
import type { ModelCreateRequest, ModelMetadata, ModelTier, ModelType, RouterStatusResponse } from '../types';

const tierColors: Record<string, string> = {
  small: 'bg-emerald-500/20 text-emerald-300',
  medium: 'bg-amber-500/20 text-amber-300',
  strong: 'bg-rose-500/20 text-rose-300',
};

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
  enabled: true,
  avg_latency_ms: 100,
  quality_score: 0.85,
};

export function ModelsPage() {
  const [models, setModels] = useState<ModelMetadata[]>([]);
  const [routerStatus, setRouterStatus] = useState<RouterStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<ModelCreateRequest>(emptyForm);
  const [detailModel, setDetailModel] = useState<ModelMetadata | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [modelsData, statusData] = await Promise.all([fetchModels(), fetchRouterStatus()]);
      setModels(modelsData);
      setRouterStatus(statusData);
    } catch {
      setError('Failed to load model registry. Ensure the backend is running on port 8000.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const toggleModel = async (model: ModelMetadata) => {
    try {
      const updated = model.enabled ? await disableModel(model.id) : await enableModel(model.id);
      setModels((prev) => prev.map((m) => (m.id === updated.id ? updated : m)));
      const status = await fetchRouterStatus();
      setRouterStatus(status);
    } catch {
      setError(`Failed to ${model.enabled ? 'disable' : 'enable'} model.`);
    }
  };

  const openCreate = () => {
    setEditingId(null);
    setForm(emptyForm);
    setShowForm(true);
  };

  const openEdit = (model: ModelMetadata) => {
    setEditingId(model.id);
    setForm({
      id: model.id,
      name: model.name,
      provider: model.provider,
      type: model.type,
      tier: model.tier,
      input_cost_per_1m_tokens: model.input_cost_per_1m_tokens,
      output_cost_per_1m_tokens: model.output_cost_per_1m_tokens,
      context_window: model.context_window,
      capabilities: model.capabilities,
      enabled: model.enabled,
      avg_latency_ms: model.avg_latency_ms,
      quality_score: model.quality_score,
    });
    setShowForm(true);
  };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    try {
      if (editingId) {
        const { id: _unusedId, ...updates } = form;
        void _unusedId;
        const updated = await updateModel(editingId, updates);
        setModels((prev) => prev.map((m) => (m.id === updated.id ? updated : m)));
      } else {
        const created = await createModel(form);
        setModels((prev) => [...prev, created]);
      }
      setShowForm(false);
    } catch {
      setError(editingId ? 'Failed to update model.' : 'Failed to create model. ID may already exist.');
    }
  };

  const viewDetail = async (modelId: string) => {
    try {
      setDetailModel(await fetchModel(modelId));
    } catch {
      setError('Failed to load model details.');
    }
  };

  return (
    <div>
      <PageHeader
        title="Model Registry"
        description="Configure available LLM providers, tiers, pricing, and capabilities."
        action={
          <div className="flex gap-2">
            <button
              onClick={openCreate}
              className="flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700"
            >
              <Plus className="h-4 w-4" />
              Add Model
            </button>
            <button
              onClick={loadData}
              className="flex items-center gap-2 rounded-lg border border-slate-700 px-4 py-2 text-sm text-slate-300 hover:bg-slate-800"
            >
              <RefreshCw className="h-4 w-4" />
              Refresh
            </button>
          </div>
        }
      />

      {routerStatus && (
        <div className="mb-6 grid grid-cols-1 gap-4 md:grid-cols-4">
          <StatCard label="Total Models" value={routerStatus.total_models} />
          <StatCard label="Enabled Models" value={routerStatus.enabled_models} />
          <StatCard label="Router Type" value={routerStatus.router_type} />
          <StatCard label="Quality Floor" value={`${(routerStatus.quality_floor * 100).toFixed(0)}%`} />
        </div>
      )}

      {error && <ErrorBanner message={error} />}

      {loading ? (
        <p className="text-slate-400">Loading models...</p>
      ) : (
        <div className="overflow-hidden rounded-xl border border-slate-800">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-900/80 text-slate-400">
              <tr>
                <th className="px-4 py-3 font-medium">Model</th>
                <th className="px-4 py-3 font-medium">Provider</th>
                <th className="px-4 py-3 font-medium">Tier</th>
                <th className="px-4 py-3 font-medium">Latency</th>
                <th className="px-4 py-3 font-medium">Quality</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {models.map((model) => (
                <tr key={model.id} className="border-t border-slate-800 hover:bg-slate-900/40">
                  <td className="px-4 py-3">
                    <div className="font-medium text-white">{model.name}</div>
                    <div className="text-xs text-slate-500">{model.id}</div>
                  </td>
                  <td className="px-4 py-3 capitalize text-slate-300">{model.provider}</td>
                  <td className="px-4 py-3">
                    <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${tierColors[model.tier]}`}>
                      {model.tier}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-slate-300">{model.avg_latency_ms.toFixed(0)} ms</td>
                  <td className="px-4 py-3 text-slate-300">{(model.quality_score * 100).toFixed(0)}%</td>
                  <td className="px-4 py-3">
                    <span
                      className={`rounded-full px-2.5 py-1 text-xs ${
                        model.enabled ? 'bg-emerald-500/20 text-emerald-300' : 'bg-slate-700 text-slate-400'
                      }`}
                    >
                      {model.enabled ? 'Enabled' : 'Disabled'}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <button onClick={() => viewDetail(model.id)} className="text-slate-400 hover:text-white" title="View">
                        <Eye className="h-4 w-4" />
                      </button>
                      <button onClick={() => openEdit(model)} className="text-xs text-brand-300 hover:text-brand-200">
                        Edit
                      </button>
                      <button onClick={() => toggleModel(model)} className="text-slate-400 hover:text-white">
                        {model.enabled ? (
                          <ToggleRight className="h-5 w-5 text-emerald-400" />
                        ) : (
                          <ToggleLeft className="h-5 w-5" />
                        )}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <form
            onSubmit={handleSubmit}
            className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-xl border border-slate-700 bg-slate-900 p-6"
          >
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-lg font-medium text-white">{editingId ? 'Edit Model' : 'Add Model'}</h3>
              <button type="button" onClick={() => setShowForm(false)} className="text-slate-400 hover:text-white">
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="space-y-3">
              <input
                required
                disabled={!!editingId}
                placeholder="Model ID"
                value={form.id}
                onChange={(e) => setForm({ ...form, id: e.target.value })}
                className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white disabled:opacity-50"
              />
              <input
                required
                placeholder="Display name"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
              />
              <div className="grid grid-cols-2 gap-3">
                <input
                  placeholder="Provider"
                  value={form.provider}
                  onChange={(e) => setForm({ ...form, provider: e.target.value })}
                  className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
                />
                <select
                  value={form.tier}
                  onChange={(e) => setForm({ ...form, tier: e.target.value as ModelTier })}
                  className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
                >
                  <option value="small">Small</option>
                  <option value="medium">Medium</option>
                  <option value="strong">Strong</option>
                </select>
              </div>
              <select
                value={form.type}
                onChange={(e) => setForm({ ...form, type: e.target.value as ModelType })}
                className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
              >
                <option value="api">API</option>
                <option value="local">Local</option>
                <option value="open_source">Open Source</option>
              </select>
              <div className="grid grid-cols-2 gap-3">
                <input
                  type="number"
                  step="0.01"
                  placeholder="Input cost / 1M"
                  value={form.input_cost_per_1m_tokens}
                  onChange={(e) => setForm({ ...form, input_cost_per_1m_tokens: Number(e.target.value) })}
                  className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
                />
                <input
                  type="number"
                  step="0.01"
                  placeholder="Output cost / 1M"
                  value={form.output_cost_per_1m_tokens}
                  onChange={(e) => setForm({ ...form, output_cost_per_1m_tokens: Number(e.target.value) })}
                  className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <input
                  type="number"
                  placeholder="Context window"
                  value={form.context_window}
                  onChange={(e) => setForm({ ...form, context_window: Number(e.target.value) })}
                  className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
                />
                <input
                  type="number"
                  step="0.01"
                  placeholder="Quality score (0-1)"
                  value={form.quality_score}
                  onChange={(e) => setForm({ ...form, quality_score: Number(e.target.value) })}
                  className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
                />
              </div>
            </div>
            <button
              type="submit"
              className="mt-4 w-full rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700"
            >
              {editingId ? 'Save Changes' : 'Create Model'}
            </button>
          </form>
        </div>
      )}

      {detailModel && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="w-full max-w-md rounded-xl border border-slate-700 bg-slate-900 p-6">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-lg font-medium text-white">{detailModel.name}</h3>
              <button onClick={() => setDetailModel(null)} className="text-slate-400 hover:text-white">
                <X className="h-5 w-5" />
              </button>
            </div>
            <dl className="space-y-2 text-sm">
              <div className="flex justify-between"><dt className="text-slate-400">ID</dt><dd className="text-white">{detailModel.id}</dd></div>
              <div className="flex justify-between"><dt className="text-slate-400">Provider</dt><dd className="capitalize text-white">{detailModel.provider}</dd></div>
              <div className="flex justify-between"><dt className="text-slate-400">Tier</dt><dd className="capitalize text-white">{detailModel.tier}</dd></div>
              <div className="flex justify-between"><dt className="text-slate-400">Context</dt><dd className="text-white">{detailModel.context_window.toLocaleString()}</dd></div>
              <div className="flex justify-between"><dt className="text-slate-400">Latency</dt><dd className="text-white">{detailModel.avg_latency_ms} ms</dd></div>
              <div className="flex justify-between"><dt className="text-slate-400">Quality</dt><dd className="text-white">{(detailModel.quality_score * 100).toFixed(0)}%</dd></div>
            </dl>
            <div className="mt-4">
              <p className="text-xs text-slate-400">Capabilities</p>
              <div className="mt-2 flex flex-wrap gap-2">
                {detailModel.capabilities.map((cap) => (
                  <span key={cap} className="rounded-full bg-slate-800 px-2 py-1 text-xs text-slate-300">{cap}</span>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
