import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import type { LucideIcon } from 'lucide-react';
import {
  Activity,
  ArrowRight,
  Bot,
  ExternalLink,
  FlaskConical,
  HeartPulse,
  Route,
  ShieldCheck,
} from 'lucide-react';
import { Badge } from '../components/Badge';
import { Button } from '../components/Button';
import { Card } from '../components/Card';
import { ErrorBanner } from '../components/ErrorBanner';
import { PageHeader } from '../components/PageHeader';
import { fetchHealth, fetchModelHealth, fetchModels, fetchRouterStatus } from '../services/api';
import type { HealthResponse, ModelHealthStatus, ModelMetadata, RouterStatusResponse } from '../types';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '';

function SkeletonBlock({ className = '' }: { className?: string }) {
  return <div className={`animate-pulse rounded-lg bg-surface-3 ${className}`} />;
}

interface SettingRowProps {
  label: string;
  description?: string;
  value?: React.ReactNode;
}

function SettingRow({ label, description, value }: SettingRowProps) {
  return (
    <div className="flex flex-col gap-1 border-b border-line-subtle py-3 last:border-b-0 sm:flex-row sm:items-start sm:justify-between sm:gap-6">
      <div className="sm:max-w-[65%]">
        <p className="text-sm text-ink-primary">{label}</p>
        {description && <p className="mt-0.5 text-xs text-ink-muted">{description}</p>}
      </div>
      <div className="flex shrink-0 items-center gap-2 sm:justify-end">
        <div className="text-sm font-medium text-ink-primary">{value ?? '—'}</div>
      </div>
    </div>
  );
}

interface SectionCardProps {
  title: string;
  description?: string;
  icon: LucideIcon;
  children: React.ReactNode;
}

function SectionCard({ title, description, icon: Icon, children }: SectionCardProps) {
  return (
    <Card>
      <div className="mb-1 flex items-center gap-2">
        <Icon className="h-4 w-4 text-ink-secondary" />
        <h3 className="text-sm font-medium text-ink-primary">{title}</h3>
      </div>
      {description && <p className="mb-2 text-xs text-ink-muted">{description}</p>}
      <div>{children}</div>
    </Card>
  );
}

export function SettingsPage() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [routerStatus, setRouterStatus] = useState<RouterStatusResponse | null>(null);
  const [models, setModels] = useState<ModelMetadata[]>([]);
  const [modelHealth, setModelHealth] = useState<ModelHealthStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [healthData, statusData, modelsData, healthList] = await Promise.all([
        fetchHealth().catch(() => null),
        fetchRouterStatus().catch(() => null),
        fetchModels().catch(() => []),
        fetchModelHealth().catch(() => []),
      ]);
      setHealth(healthData);
      setRouterStatus(statusData);
      setModels(modelsData);
      setModelHealth(healthList);
      setError(null);
    } catch {
      setError('Failed to load gateway configuration. Ensure the backend is running.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const isOnline = health?.status === 'ok';

  const providerSummary = models.reduce<Record<string, { total: number; enabled: number }>>((acc, model) => {
    const entry = acc[model.provider] ?? { total: 0, enabled: 0 };
    entry.total += 1;
    if (model.enabled) entry.enabled += 1;
    acc[model.provider] = entry;
    return acc;
  }, {});

  const healthyCount = modelHealth.filter((m) => m.state === 'closed').length;
  const openCount = modelHealth.filter((m) => m.state === 'open').length;
  const halfOpenCount = modelHealth.filter((m) => m.state === 'half_open').length;

  return (
    <div>
      <PageHeader
        title="Gateway Configuration"
        description="How the Adaptive AI Gateway is configured, and what's safe to change from here."
        action={
          <a href={`${API_BASE_URL}/docs`} target="_blank" rel="noreferrer">
            <Button variant="secondary" size="sm">
              <ExternalLink className="h-4 w-4" />
              API Docs
            </Button>
          </a>
        }
      />

      {error && <ErrorBanner message={error} variant="error" />}

      {/* Compact gateway status strip */}
      <Card className="mb-6">
        {loading ? (
          <div className="flex flex-wrap items-center gap-6">
            <SkeletonBlock className="h-6 w-32" />
            <SkeletonBlock className="h-6 w-24" />
            <SkeletonBlock className="h-6 w-24" />
          </div>
        ) : (
          <div className="flex flex-wrap items-center gap-x-8 gap-y-3 text-sm">
            <div className="flex items-center gap-2">
              <Badge variant={isOnline ? 'success' : 'error'}>
                <span
                  className={`mr-1.5 h-1.5 w-1.5 rounded-full ${isOnline ? 'bg-success-400' : 'bg-danger-400'}`}
                />
                {isOnline ? 'Gateway Online' : 'Gateway Offline'}
              </Badge>
            </div>
            <div>
              <span className="text-ink-muted">Application</span>{' '}
              <span className="text-ink-primary">{health?.app_name ?? '—'}</span>
            </div>
            <div>
              <span className="text-ink-muted">Version</span>{' '}
              <span className="text-ink-primary">{health?.version ?? '—'}</span>
            </div>
            <div>
              <span className="text-ink-muted">Environment</span>{' '}
              <span className="capitalize text-ink-primary">{health?.environment ?? '—'}</span>
            </div>
            <div>
              <span className="text-ink-muted">Router</span>{' '}
              <span className="text-ink-primary">{routerStatus?.router_type ?? '—'}</span>
            </div>
          </div>
        )}
      </Card>

      {loading ? (
        <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Card key={i}>
              <SkeletonBlock className="h-4 w-32" />
              <SkeletonBlock className="mt-4 h-24 w-full" />
            </Card>
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
          {/* Gateway */}
          <SectionCard icon={ShieldCheck} title="Gateway" description="Runtime identity and access control for this deployment.">
            <SettingRow
              label="Status"
              value={
                <Badge variant={isOnline ? 'success' : 'error'}>{health?.status ?? 'unknown'}</Badge>
              }
            />
            <SettingRow label="Environment" value={health?.environment ?? '—'} description="APP_ENV" />
            <SettingRow
              label="Bearer Authentication"
              description="Optional token required on /v1/* OpenAI-compatible endpoints."
              value={routerStatus ? (routerStatus.auth_enabled ? 'Required' : 'Off') : '—'}
            />
          </SectionCard>

          {/* Routing */}
          <SectionCard icon={Route} title="Routing" description="How the gateway picks a model for each request.">
            <SettingRow label="Active Strategy" value={routerStatus?.router_type ?? '—'} />
            <SettingRow
              label="Quality Floor"
              description="Minimum acceptable response quality before escalation."
              value={routerStatus ? `${(routerStatus.quality_floor * 100).toFixed(0)}%` : '—'}
            />
            <SettingRow
              label="Cost Priority"
              description="Weight given to cost when comparing candidate models."
              value={routerStatus?.cost_priority ?? '—'}
            />
            <SettingRow
              label="Latency Priority"
              description="Weight given to latency when comparing candidate models."
              value={routerStatus?.latency_priority ?? '—'}
            />
            <SettingRow
              label="Routing Threshold"
              description="Confidence threshold used by ML-based routers (tfidf / embedding / bert)."
              value={routerStatus?.routing_threshold ?? '—'}
            />
            <SettingRow
              label="Fallback"
              value={routerStatus ? (routerStatus.fallback_enabled ? 'Enabled' : 'Disabled') : '—'}
            />
            <SettingRow label="Max Fallback Attempts" value={routerStatus?.max_fallback_attempts ?? '—'} />
            <SettingRow
              label="Fallback Quality Threshold"
              value={
                routerStatus?.fallback_on_quality_below != null
                  ? `${(routerStatus.fallback_on_quality_below * 100).toFixed(0)}%`
                  : 'Disabled'
              }
            />
            <SettingRow label="Escalation Strategy" value={routerStatus?.fallback_escalation ?? '—'} />
          </SectionCard>

          {/* Models & Providers */}
          <SectionCard icon={Bot} title="Models & Providers" description="Registered models available for routing.">
            <SettingRow
              label="Enabled Models"
              value={routerStatus ? `${routerStatus.enabled_models} / ${routerStatus.total_models}` : '—'}
            />
            {Object.keys(providerSummary).length === 0 ? (
              <p className="py-3 text-sm text-ink-muted">No models registered yet.</p>
            ) : (
              Object.entries(providerSummary).map(([provider, counts]) => (
                <SettingRow
                  key={provider}
                  label={provider}
                  value={`${counts.enabled} / ${counts.total} enabled`}
                />
              ))
            )}
            <SettingRow
              label="Provider Credentials"
              description="Which provider API keys are configured on the backend. Key values are never exposed."
              value={
                routerStatus ? (
                  <div className="flex flex-wrap justify-end gap-1.5">
                    {Object.entries(routerStatus.configured_providers).map(([provider, configured]) => (
                      <Badge key={provider} variant={configured ? 'success' : 'neutral'}>
                        {provider.replace('_', ' ')}: {configured ? 'set' : 'not set'}
                      </Badge>
                    ))}
                  </div>
                ) : (
                  '—'
                )
              }
            />
            <Link to="/models" className="mt-3 inline-block">
              <Button variant="ghost" size="sm">
                Open Model Registry
                <ArrowRight className="h-3.5 w-3.5" />
              </Button>
            </Link>
          </SectionCard>

          {/* Health & Reliability */}
          <SectionCard
            icon={HeartPulse}
            title="Health & Reliability"
            description="Circuit-breaker behavior that isolates failing models."
          >
            <SettingRow
              label="Live Circuit State"
              value={
                <div className="flex items-center gap-1.5">
                  <Badge variant="closed">{healthyCount} healthy</Badge>
                  {(openCount > 0 || halfOpenCount > 0) && (
                    <>
                      <Badge variant="half_open">{halfOpenCount} recovering</Badge>
                      <Badge variant="open">{openCount} open</Badge>
                    </>
                  )}
                </div>
              }
            />
            <SettingRow
              label="Failure Threshold"
              description="Consecutive failures before a model's circuit opens."
              value={routerStatus?.health_failure_threshold ?? '—'}
            />
            <SettingRow
              label="Cooldown Period"
              description="Time an open circuit waits before a health-check retry."
              value={routerStatus ? `${routerStatus.health_cooldown_seconds}s` : '—'}
            />
            <Link to="/models" className="mt-3 inline-block">
              <Button variant="ghost" size="sm">
                View Model Health
                <ArrowRight className="h-3.5 w-3.5" />
              </Button>
            </Link>
          </SectionCard>

          {/* Evaluation */}
          <SectionCard
            icon={FlaskConical}
            title="Evaluation"
            description="Automated response quality scoring."
          >
            <SettingRow
              label="Judge Provider"
              description="LLM used to score response quality."
              value={routerStatus?.judge_provider ?? '—'}
            />
            <SettingRow
              label="Judge Model"
              value={
                routerStatus
                  ? routerStatus.judge_provider === 'mock'
                    ? 'Heuristic (no LLM)'
                    : routerStatus.judge_model_id
                  : '—'
              }
            />
            <SettingRow
              label="Evaluate on Chat"
              description="Whether every chat response is auto-scored."
              value={routerStatus ? (routerStatus.evaluate_on_chat ? 'On' : 'Off') : '—'}
            />
            <p className="mt-2 text-xs text-ink-muted">
              On-demand scoring is always available via the Chat Playground&rsquo;s Evaluate Response action.
            </p>
          </SectionCard>

          {/* API & Integration */}
          <SectionCard icon={Activity} title="API & Integration" description="Programmatic access to this gateway.">
            <SettingRow label="Interactive API Docs" value={`${API_BASE_URL || '(same origin)'}/docs`} />
            <SettingRow label="OpenAI-Compatible Endpoint" value={`${API_BASE_URL || '(same origin)'}/v1`} />
            <SettingRow label="Chat Completions" value="POST /v1/chat/completions" />
            <SettingRow label="List Models" value="GET /v1/models" />
            <SettingRow label="Quality Override Header" value="X-Quality-Floor" />
          </SectionCard>
        </div>
      )}
    </div>
  );
}
