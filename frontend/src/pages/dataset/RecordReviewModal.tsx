import { FormEvent, useState } from 'react';
import { Badge } from '../../components/Badge';
import { Button } from '../../components/Button';
import { ErrorBanner } from '../../components/ErrorBanner';
import { Input } from '../../components/Input';
import { Modal } from '../../components/Modal';
import { Select } from '../../components/Select';
import type { PreferenceRecord } from '../../types';
import { EVAL_SOURCE_BADGE, EVAL_SOURCE_LABEL, formatTaskType, TIER_BADGE } from './format';

interface RecordReviewModalProps {
  record: PreferenceRecord;
  submitting: boolean;
  errorMessage: string | null;
  onClose: () => void;
  onSubmit: (form: {
    small_score: number;
    medium_score: number;
    strong_score: number;
    preferred_model: 'small' | 'medium' | 'strong';
    notes: string;
  }) => void;
}

const TIERS = [
  { key: 'small' as const, label: 'Small', response: 'small_response' as const, model: 'small_model_id' as const },
  { key: 'medium' as const, label: 'Medium', response: 'medium_response' as const, model: 'medium_model_id' as const },
  { key: 'strong' as const, label: 'Strong', response: 'strong_response' as const, model: 'strong_model_id' as const },
];

export function RecordReviewModal({ record, submitting, errorMessage, onClose, onSubmit }: RecordReviewModalProps) {
  const [form, setForm] = useState({
    small_score: record.small_score,
    medium_score: record.medium_score,
    strong_score: record.strong_score,
    preferred_model: record.preferred_model,
    notes: record.human_notes ?? '',
  });

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    onSubmit(form);
  };

  return (
    <Modal open onClose={onClose} title="Review preference record" maxWidth="max-w-2xl">
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Badge variant="neutral">{formatTaskType(record.task_type)}</Badge>
        <Badge variant={EVAL_SOURCE_BADGE[record.evaluation_source] ?? 'neutral'}>
          {EVAL_SOURCE_LABEL[record.evaluation_source] ?? record.evaluation_source}
        </Badge>
        <span className="text-xs text-ink-muted">Quality floor {(record.quality_floor * 100).toFixed(0)}%</span>
      </div>

      <p className="mb-4 rounded-lg border border-line bg-surface-1/60 px-3 py-2.5 text-sm text-ink-primary">
        {record.prompt}
      </p>

      <div className="mb-5 space-y-3">
        {TIERS.map(({ key, label, response, model }) => {
          const text = record[response];
          if (!text) return null;
          const sufficient = record[`${key}_sufficient` as const];
          const score = record[`${key}_score` as const];
          return (
            <div key={key} className="rounded-lg border border-line">
              <div className="flex items-center justify-between gap-2 border-b border-line bg-surface-3/40 px-3 py-2">
                <div className="flex items-center gap-2">
                  <Badge variant={TIER_BADGE[key]}>{label}</Badge>
                  {record[model] && <span className="font-mono text-xs text-ink-muted">{record[model]}</span>}
                </div>
                <span className={`text-xs font-medium ${sufficient ? 'text-success-300' : 'text-ink-muted'}`}>
                  {(score * 100).toFixed(0)}% {sufficient ? '· meets floor' : ''}
                </span>
              </div>
              <p className="max-h-40 overflow-y-auto whitespace-pre-wrap px-3 py-2.5 text-xs text-ink-secondary">
                {text}
              </p>
            </div>
          );
        })}
      </div>

      <form onSubmit={handleSubmit} className="space-y-4 border-t border-line pt-4">
        <p className="text-xs font-medium text-ink-secondary">Human evaluation override</p>
        {errorMessage && <ErrorBanner message={errorMessage} className="mb-0" />}
        <div className="grid grid-cols-3 gap-3">
          {(['small_score', 'medium_score', 'strong_score'] as const).map((key) => (
            <label key={key} className="block">
              <span className="mb-1 block text-xs text-ink-muted capitalize">{key.replace('_score', '')}</span>
              <Input
                type="number"
                min={0}
                max={1}
                step={0.05}
                value={form[key]}
                onChange={(event) => setForm({ ...form, [key]: Number(event.target.value) })}
              />
            </label>
          ))}
        </div>
        <label className="block">
          <span className="mb-1 block text-xs text-ink-muted">Preferred model</span>
          <Select
            value={form.preferred_model}
            onChange={(event) =>
              setForm({ ...form, preferred_model: event.target.value as 'small' | 'medium' | 'strong' })
            }
          >
            <option value="small">Small</option>
            <option value="medium">Medium</option>
            <option value="strong">Strong</option>
          </Select>
        </label>
        <label className="block">
          <span className="mb-1 block text-xs text-ink-muted">Notes (optional)</span>
          <textarea
            value={form.notes}
            onChange={(event) => setForm({ ...form, notes: event.target.value })}
            rows={2}
            className="w-full rounded-control border border-line bg-surface-1 px-3 py-2 text-sm text-ink-primary placeholder:text-ink-muted focus:outline-none focus:ring-2 focus:ring-brand-500/50"
          />
        </label>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={submitting}>
            Save human evaluation
          </Button>
        </div>
      </form>
    </Modal>
  );
}
