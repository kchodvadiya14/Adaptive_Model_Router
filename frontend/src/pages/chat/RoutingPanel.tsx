import type { ReactNode } from 'react';
import { ShieldAlert } from 'lucide-react';
import { Badge } from '../../components/Badge';
import { Card } from '../../components/Card';
import type {
  ChatResponse,
  FallbackInfo,
  ModelHealthStatus,
  ModelMetadata,
  ModelTier,
  RoutingDecision,
} from '../../types';
import { formatCost, formatMs, formatPercent, HEALTH_BADGE_VARIANT, HEALTH_LABEL } from '../models/format';

interface RoutingPanelProps {
  routing: RoutingDecision | null;
  response: ChatResponse | null;
  selectedModelMeta: ModelMetadata | undefined;
  selectedHealth: ModelHealthStatus | undefined;
  requestedCapabilities: string[];
  pinnedModel: boolean;
  previewOnly: boolean;
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-3 py-2">
      <dt className="shrink-0 text-xs text-ink-muted">{label}</dt>
      <dd className="text-right text-sm text-ink-primary">{children}</dd>
    </div>
  );
}

function SectionTitle({ children }: { children: ReactNode }) {
  return <h4 className="mb-1 text-xs font-medium uppercase tracking-wide text-ink-muted">{children}</h4>;
}

function formatTask(task: string): string {
  return task.replace(/_/g, ' ');
}

function fallbackSummary(fallback: FallbackInfo): string {
  const reason = fallback.escalation_reason?.replace(/_/g, ' ');
  const fromTo = `${fallback.original_model} → ${fallback.final_model}`;
  return reason ? `${fromTo} (${reason})` : fromTo;
}

export function RoutingPanel({
  routing,
  response,
  selectedModelMeta,
  selectedHealth,
  requestedCapabilities,
  pinnedModel,
  previewOnly,
}: RoutingPanelProps) {
  const selectedId = response?.model ?? routing?.selected_model;
  const otherTiers = routing?.tier_qualities.filter((tier) => tier.model_id !== routing.selected_model) ?? [];
  const featureEntries = routing ? Object.entries(routing.features).filter(([, value]) => value !== null && value !== '') : [];

  return (
    <div className="space-y-4 lg:sticky lg:top-6">
      <Card>
        <div className="mb-3 flex items-center justify-between gap-2">
          <h3 className="text-sm font-medium text-ink-primary">Request metadata</h3>
          {response?.fallback?.used && (
            <Badge variant="warning">
              <span className="inline-flex items-center gap-1">
                <ShieldAlert className="h-3 w-3" />
                Fallback
              </span>
            </Badge>
          )}
        </div>
        {response ? (
          <dl className="divide-y divide-line">
            {response.request_id && (
              <Row label="Request ID">
                <span className="break-all font-mono text-xs">{response.request_id}</span>
              </Row>
            )}
            <Row label="Selected model">
              <span className="font-medium">{response.model_name || response.model}</span>
            </Row>
            <Row label="Provider">{response.provider}</Row>
            <Row label="Tier">
              <Badge variant={response.tier as ModelTier}>{response.tier}</Badge>
            </Row>
            <Row label="Latency">{formatMs(response.latency_ms)}</Row>
            <Row label="Estimated cost">{formatCost(response.cost.total_cost)}</Row>
            <Row label="Tokens">{response.usage.total_tokens.toLocaleString()}</Row>
            <Row label="Fallback used">{response.fallback?.used ? 'Yes' : 'No'}</Row>
            {response.fallback?.used && <Row label="Escalation">{fallbackSummary(response.fallback)}</Row>}
          </dl>
        ) : (
          <p className="text-sm text-ink-muted">
            {previewOnly
              ? 'Preview shows routing only. Send the prompt to capture request ID, latency, and cost.'
              : 'Send a prompt to see request ID, selected model, provider, latency, and cost.'}
          </p>
        )}
      </Card>

      <Card>
        <div className="mb-3 flex items-center justify-between gap-2">
          <h3 className="text-sm font-medium text-ink-primary">Why this model?</h3>
          {routing && <Badge variant={previewOnly ? 'neutral' : 'info'}>{previewOnly ? 'Preview' : 'Routed'}</Badge>}
        </div>

        {!routing ? (
          response ? (
            <p className="text-sm text-ink-muted">Routing details unavailable for this request.</p>
          ) : (
            <p className="text-sm text-ink-muted">
              {pinnedModel
                ? 'Pinning a model skips adaptive routing. Switch to Auto to see why a model is selected.'
                : 'Send a prompt with Auto routing, or preview routing, to see why a model was selected.'}
            </p>
          )
        ) : (
          <div className="space-y-4">
            <dl className="divide-y divide-line">
              <Row label="Task">
                <span className="capitalize">{formatTask(routing.task_type)}</span>
              </Row>
              <Row label="Difficulty">{formatPercent(routing.difficulty, 0)}</Row>
              <Row label="Confidence">{formatPercent(routing.confidence, 0)}</Row>
              <Row label="Capabilities">
                <div className="flex flex-wrap justify-end gap-1">
                  {requestedCapabilities.length > 0 ? (
                    requestedCapabilities.map((cap) => (
                      <Badge key={cap} variant="info">
                        {cap}
                      </Badge>
                    ))
                  ) : (
                    <span className="text-ink-muted">None requested</span>
                  )}
                </div>
              </Row>
              {selectedModelMeta && selectedModelMeta.capabilities.length > 0 && (
                <Row label="Model capabilities">
                  <div className="flex flex-wrap justify-end gap-1">
                    {selectedModelMeta.capabilities.map((cap) => (
                      <Badge key={cap} variant="neutral">
                        {cap}
                      </Badge>
                    ))}
                  </div>
                </Row>
              )}
              <Row label="Selected model">
                <div>
                  <p className="font-medium">{selectedModelMeta?.name ?? routing.selected_model}</p>
                  <p className="font-mono text-xs text-ink-muted">{routing.selected_model}</p>
                </div>
              </Row>
              {selectedHealth && (
                <Row label="Health">
                  <Badge variant={HEALTH_BADGE_VARIANT[selectedHealth.state]}>
                    {HEALTH_LABEL[selectedHealth.state]}
                  </Badge>
                </Row>
              )}
              <Row label="Quality estimate">{formatPercent(routing.estimated_quality, 0)}</Row>
              <Row label="Est. cost">{formatCost(routing.estimated_cost)}</Row>
              <Row label="Strong-model cost">{formatCost(routing.strong_model_baseline_cost)}</Row>
              <Row label="Saved vs strong">
                <span className="text-success-300">
                  {formatCost(routing.cost_saved_vs_strong)}
                  {routing.strong_model_baseline_cost > 0 &&
                    ` (${formatPercent(routing.cost_saved_vs_strong / routing.strong_model_baseline_cost, 0)})`}
                </span>
              </Row>
              {response && <Row label="Actual latency">{formatMs(response.latency_ms)}</Row>}
              {routing.preferred_model && (
                <Row label="Preferred model">
                  {routing.preferred_model_honored ? 'Honored' : `Not used (${routing.preferred_model})`}
                </Row>
              )}
            </dl>

            {routing.reason && (
              <div>
                <SectionTitle>Decision</SectionTitle>
                <p className="text-sm leading-relaxed text-ink-secondary">{routing.reason}</p>
              </div>
            )}

            {routing.explanation.length > 0 && (
              <div>
                <SectionTitle>Explanation</SectionTitle>
                <ul className="space-y-2 text-sm text-ink-secondary">
                  {routing.explanation.map((line) => (
                    <li key={line} className="flex gap-2">
                      <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-brand-400" />
                      <span>{line}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </Card>

      {routing && otherTiers.length > 0 && (
        <Card>
          <SectionTitle>Other tiers considered</SectionTitle>
          <div className="mt-3 space-y-2">
            {otherTiers.map((tier) => (
              <div key={tier.tier} className="rounded-lg border border-line bg-surface-1 px-3 py-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm capitalize text-ink-primary">{tier.tier}</span>
                  <Badge variant={tier.meets_quality_floor ? 'success' : 'warning'}>
                    {tier.meets_quality_floor ? 'meets floor' : 'below floor'}
                  </Badge>
                </div>
                <div className="mt-1 flex justify-between text-xs text-ink-muted">
                  <span>{tier.model_id ?? 'No model'}</span>
                  <span>
                    {formatPercent(tier.expected_quality, 0)}
                    {tier.quality_samples ? ` (measured, n=${tier.quality_samples})` : ' (assumed)'} ·{' '}
                    {formatCost(tier.estimated_cost)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {routing && featureEntries.length > 0 && (
        <Card>
          <SectionTitle>Prompt features</SectionTitle>
          <div className="mt-3 flex flex-wrap gap-2">
            {featureEntries.map(([key, value]) => (
              <span key={key} className="rounded-full border border-line bg-surface-1 px-2 py-1 text-xs text-ink-secondary">
                {key.replace(/_/g, ' ')}: {String(value)}
              </span>
            ))}
          </div>
        </Card>
      )}

      {response?.fallback?.used && response.fallback.attempts.length > 0 && (
        <Card>
          <SectionTitle>Fallback attempts</SectionTitle>
          <ul className="mt-3 space-y-2 text-xs text-ink-secondary">
            {response.fallback.attempts.map((attempt, index) => (
              <li key={`${attempt.model_id}-${index}`} className="flex justify-between gap-2">
                <span className="font-mono">{attempt.model_id}</span>
                <span>
                  {attempt.success ? 'success' : attempt.reason || 'failed'}
                  {attempt.latency_ms != null ? ` · ${formatMs(attempt.latency_ms)}` : ''}
                </span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {selectedId && !selectedHealth && routing && (
        <p className="px-1 text-xs text-ink-muted">Live health for the selected model is not available.</p>
      )}
    </div>
  );
}
