import { FormEvent, useState } from 'react';
import { Button } from '../../components/Button';
import { ErrorBanner } from '../../components/ErrorBanner';
import { Input } from '../../components/Input';
import { Modal } from '../../components/Modal';
import { Select } from '../../components/Select';
import type { ModelCreateRequest, ModelType, ModelTier } from '../../types';

interface ModelFormModalProps {
  open: boolean;
  editingId: string | null;
  initialValue: ModelCreateRequest;
  submitting: boolean;
  errorMessage: string | null;
  onClose: () => void;
  onSubmit: (form: ModelCreateRequest) => void;
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-xs font-medium text-ink-secondary">{label}</span>
      {children}
    </label>
  );
}

export function ModelFormModal({
  open,
  editingId,
  initialValue,
  submitting,
  errorMessage,
  onClose,
  onSubmit,
}: ModelFormModalProps) {
  // The parent remounts this component (via a `key` keyed on editingId) whenever a
  // different model is opened or the form switches between create/edit, so this local
  // state only ever needs to be seeded once per mount.
  const [form, setForm] = useState<ModelCreateRequest>(initialValue);

  const capabilitiesText = (form.capabilities ?? []).join(', ');

  const update = <K extends keyof ModelCreateRequest>(key: K, value: ModelCreateRequest[K]) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    onSubmit(form);
  };

  return (
    <Modal open={open} onClose={onClose} title={editingId ? `Edit ${editingId}` : 'Add Model'} maxWidth="max-w-2xl">
      <form onSubmit={handleSubmit} className="space-y-5">
        {errorMessage && <ErrorBanner message={errorMessage} className="mb-0" />}

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Model ID">
            <Input
              required
              disabled={!!editingId}
              placeholder="gpt-4o-mini"
              value={form.id}
              onChange={(e) => update('id', e.target.value)}
            />
          </Field>
          <Field label="Display name">
            <Input
              required
              placeholder="GPT-4o Mini"
              value={form.name}
              onChange={(e) => update('name', e.target.value)}
            />
          </Field>
          <Field label="Provider">
            <Input
              required
              placeholder="openai"
              value={form.provider}
              onChange={(e) => update('provider', e.target.value)}
            />
          </Field>
          <Field label="Deployment type">
            <Select value={form.type} onChange={(e) => update('type', e.target.value as ModelType)}>
              <option value="api">API</option>
              <option value="local">Local</option>
              <option value="open_source">Open Source</option>
            </Select>
          </Field>
          <Field label="Routing tier">
            <Select value={form.tier} onChange={(e) => update('tier', e.target.value as ModelTier)}>
              <option value="small">Small</option>
              <option value="medium">Medium</option>
              <option value="strong">Strong</option>
            </Select>
          </Field>
          <Field label="Context window (tokens)">
            <Input
              required
              type="number"
              min={1}
              value={form.context_window}
              onChange={(e) => update('context_window', Number(e.target.value))}
            />
          </Field>
          <Field label="Input cost / 1M tokens ($)">
            <Input
              required
              type="number"
              step="0.01"
              min={0}
              value={form.input_cost_per_1m_tokens}
              onChange={(e) => update('input_cost_per_1m_tokens', Number(e.target.value))}
            />
          </Field>
          <Field label="Output cost / 1M tokens ($)">
            <Input
              required
              type="number"
              step="0.01"
              min={0}
              value={form.output_cost_per_1m_tokens}
              onChange={(e) => update('output_cost_per_1m_tokens', Number(e.target.value))}
            />
          </Field>
          <Field label="Avg. latency (ms)">
            <Input
              type="number"
              min={0}
              value={form.avg_latency_ms ?? 0}
              onChange={(e) => update('avg_latency_ms', Number(e.target.value))}
            />
          </Field>
          <Field label="Quality score (0–1)">
            <Input
              type="number"
              step="0.01"
              min={0}
              max={1}
              value={form.quality_score ?? 0}
              onChange={(e) => update('quality_score', Number(e.target.value))}
            />
          </Field>
        </div>

        <Field label="Capabilities (comma-separated)">
          <Input
            placeholder="general, coding, reasoning"
            value={capabilitiesText}
            onChange={(e) =>
              update(
                'capabilities',
                e.target.value
                  .split(',')
                  .map((item) => item.trim())
                  .filter(Boolean),
              )
            }
          />
        </Field>

        <div className="flex flex-wrap gap-6">
          <label className="flex items-center gap-2 text-sm text-ink-primary">
            <input
              type="checkbox"
              className="h-4 w-4 rounded border-line bg-surface-1 accent-brand-600"
              checked={!!form.supports_vision}
              onChange={(e) => update('supports_vision', e.target.checked)}
            />
            Supports vision / image input
          </label>
          <label className="flex items-center gap-2 text-sm text-ink-primary">
            <input
              type="checkbox"
              className="h-4 w-4 rounded border-line bg-surface-1 accent-brand-600"
              checked={!!form.supports_tools}
              onChange={(e) => update('supports_tools', e.target.checked)}
            />
            Supports tool / function calling
          </label>
          <label className="flex items-center gap-2 text-sm text-ink-primary">
            <input
              type="checkbox"
              className="h-4 w-4 rounded border-line bg-surface-1 accent-brand-600"
              checked={form.enabled ?? true}
              onChange={(e) => update('enabled', e.target.checked)}
            />
            Enabled
          </label>
        </div>

        <div className="flex justify-end gap-2 border-t border-line pt-4">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={submitting}>
            {editingId ? 'Save Changes' : 'Create Model'}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
