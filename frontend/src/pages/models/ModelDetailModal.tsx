import { Activity, Clock, History, Image, Settings2, Wrench } from 'lucide-react';
import { Badge } from '../../components/Badge';
import { Modal } from '../../components/Modal';
import type { ModelHealthStatus, ModelMetadata, ModelPerformance } from '../../types';
import {
  formatCost,
  formatCountdown,
  formatMs,
  formatPercent,
  formatTimestamp,
  HEALTH_BADGE_VARIANT,
  HEALTH_LABEL,
  isPrimaryForTier,
} from './format';

interface ModelDetailModalProps {
  model: ModelMetadata | null;
  allModels: ModelMetadata[];
  health: ModelHealthStatus | undefined;
  performance: ModelPerformance | undefined;
  healthUnavailable: boolean;
  performanceUnavailable: boolean;
  onClose: () => void;
}

function Section({
  icon: Icon,
  title,
  subtitle,
  children,
}: {
  icon: typeof Settings2;
  title: string;
  subtitle: string;
  children: React.ReactNode;
}) {
  return (
    <section className="border-t border-line pt-4 first:border-t-0 first:pt-0">
      <div className="mb-3 flex items-center gap-2">
        <Icon className="h-4 w-4 text-ink-muted" />
        <h4 className="text-sm font-medium text-ink-primary">{title}</h4>
        <span className="text-xs text-ink-muted">· {subtitle}</span>
      </div>
      {children}
    </section>
  );
}

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs text-ink-muted">{label}</dt>
      <dd className="mt-0.5 text-sm text-ink-primary">{value}</dd>
    </div>
  );
}

export function ModelDetailModal({
  model,
  allModels,
  health,
  performance,
  healthUnavailable,
  performanceUnavailable,
  onClose,
}: ModelDetailModalProps) {
  if (!model) return null;

  const primary = isPrimaryForTier(model, allModels);

  return (
    <Modal
      open={!!model}
      onClose={onClose}
      maxWidth="max-w-xl"
      title={model.name}
    >
      <div className="-mt-2 mb-4 flex flex-wrap items-center gap-2">
        <span className="font-mono text-xs text-ink-muted">{model.id}</span>
        <Badge variant={model.tier}>{model.tier}</Badge>
        <Badge variant={model.enabled ? 'success' : 'neutral'}>{model.enabled ? 'Enabled' : 'Disabled'}</Badge>
        <span className="text-xs text-ink-muted">· {model.provider}</span>
      </div>

      <div className="space-y-5">
        {/* Registry metadata — the model's static configuration. */}
        <Section icon={Settings2} title="Configuration" subtitle="registry metadata">
          <dl className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-3">
            <Stat label="Type" value={<span className="capitalize">{model.type.replace('_', ' ')}</span>} />
            <Stat label="Context window" value={`${model.context_window.toLocaleString()} tok`} />
            <Stat label="Registry quality" value={formatPercent(model.quality_score, 0)} />
            <Stat label="Input cost / 1M" value={`$${model.input_cost_per_1m_tokens.toFixed(2)}`} />
            <Stat label="Output cost / 1M" value={`$${model.output_cost_per_1m_tokens.toFixed(2)}`} />
            <Stat label="Configured latency" value={formatMs(model.avg_latency_ms)} />
          </dl>
        </Section>

        {/* Capabilities — also registry metadata, called out separately per capability-aware routing. */}
        <Section icon={Wrench} title="Capabilities" subtitle="registry metadata">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant={model.supports_vision ? 'info' : 'neutral'} className="gap-1.5 normal-case">
              <Image className="h-3 w-3" /> Vision {model.supports_vision ? 'supported' : 'unsupported'}
            </Badge>
            <Badge variant={model.supports_tools ? 'info' : 'neutral'} className="gap-1.5 normal-case">
              <Wrench className="h-3 w-3" /> Tools {model.supports_tools ? 'supported' : 'unsupported'}
            </Badge>
            {model.capabilities.map((capability) => (
              <Badge key={capability} variant="neutral">
                {capability.replace('_', ' ')}
              </Badge>
            ))}
          </div>
        </Section>

        {/* Live health — the circuit breaker's current, real-time state for this model. */}
        <Section icon={Activity} title="Live Health" subtitle="circuit breaker, right now">
          {healthUnavailable ? (
            <p className="text-sm text-ink-muted">Health data unavailable — could not reach /api/health/models.</p>
          ) : health ? (
            <div className="space-y-3">
              <Badge variant={HEALTH_BADGE_VARIANT[health.state]} className="uppercase tracking-wide">
                {HEALTH_LABEL[health.state]}
              </Badge>
              <dl className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-3">
                <Stat label="Consecutive failures" value={health.consecutive_failures} />
                <Stat label="Recent failures" value={health.recent_failures} />
                <Stat label="Recent successes" value={health.recent_successes} />
                {health.state === 'open' && (
                  <Stat label="Cooldown remaining" value={formatCountdown(health.cooldown_remaining_seconds)} />
                )}
                <Stat label="Last success" value={formatTimestamp(health.last_success)} />
                <Stat label="Last failure" value={formatTimestamp(health.last_failure)} />
              </dl>
              {health.last_error && (
                <p className="rounded-lg bg-surface-3/60 px-3 py-2 text-xs text-ink-secondary">
                  Last error: {health.last_error}
                </p>
              )}
            </div>
          ) : (
            <p className="text-sm text-ink-muted">No health record yet — this model has never been attempted.</p>
          )}
        </Section>

        {/* Historical performance — aggregated from every recorded generation attempt. */}
        <Section icon={History} title="Historical Performance" subtitle="all recorded attempts">
          {performanceUnavailable ? (
            <p className="text-sm text-ink-muted">
              Performance data unavailable — could not reach /api/performance/models.
            </p>
          ) : performance ? (
            <div className="space-y-3">
              <dl className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-3">
                <Stat label="Requests" value={performance.request_count.toLocaleString()} />
                <Stat label="Success rate" value={formatPercent(performance.success_rate)} />
                <Stat label="Fallback rate" value={formatPercent(performance.fallback_rate)} />
                <Stat label="Avg. latency" value={formatMs(performance.average_latency_ms)} />
                <Stat label="Avg. quality" value={formatPercent(performance.average_quality_score)} />
                <Stat label="Avg. cost / request" value={formatCost(performance.average_estimated_cost)} />
              </dl>
              <div className="flex flex-wrap gap-1.5 text-xs text-ink-muted">
                <span className="mr-1">Outcomes:</span>
                <Badge variant="success">{performance.outcomes.success} success</Badge>
                {performance.outcomes.quality_failure > 0 && (
                  <Badge variant="warning">{performance.outcomes.quality_failure} low quality</Badge>
                )}
                {performance.outcomes.retryable_failure > 0 && (
                  <Badge variant="warning">{performance.outcomes.retryable_failure} retryable errors</Badge>
                )}
                {performance.outcomes.non_retryable_failure > 0 && (
                  <Badge variant="error">{performance.outcomes.non_retryable_failure} hard errors</Badge>
                )}
                {performance.outcomes.timeout > 0 && (
                  <Badge variant="error">{performance.outcomes.timeout} timeouts</Badge>
                )}
              </div>
              <p className="text-xs text-ink-muted">
                First seen {formatTimestamp(performance.first_seen)} · last seen {formatTimestamp(performance.last_seen)}
              </p>
            </div>
          ) : (
            <p className="text-sm text-ink-muted">No requests recorded yet for this model.</p>
          )}
        </Section>

        {/* Routing role — derived client-side from the registry, not a separate endpoint. */}
        <Section icon={Clock} title="Routing Role" subtitle="derived from the registry">
          <p className="text-sm text-ink-secondary">
            {model.enabled ? (
              primary ? (
                <>
                  This is the <span className="font-medium text-ink-primary">primary</span> model for the{' '}
                  <span className="font-medium capitalize text-ink-primary">{model.tier}</span> tier — the router
                  sends {model.tier}-tier traffic here because it is the cheapest enabled model in that tier.
                </>
              ) : (
                <>
                  This model is enabled but is <span className="font-medium text-ink-primary">not</span> the primary
                  choice for the <span className="font-medium capitalize text-ink-primary">{model.tier}</span> tier —
                  a cheaper enabled model in the same tier is used instead.
                </>
              )
            ) : (
              <>
                This model is <span className="font-medium text-ink-primary">disabled</span> and is never selected by
                routing.
              </>
            )}
          </p>
        </Section>
      </div>
    </Modal>
  );
}
