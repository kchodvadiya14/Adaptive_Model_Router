import { useEffect, useState } from 'react';
import { ExternalLink } from 'lucide-react';
import { PageHeader } from '../components/PageHeader';
import { StatCard } from '../components/StatCard';
import { fetchHealth, fetchRouterStatus } from '../services/api';
import type { HealthResponse, RouterStatusResponse } from '../types';

export function SettingsPage() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [routerStatus, setRouterStatus] = useState<RouterStatusResponse | null>(null);

  useEffect(() => {
    fetchHealth().then(setHealth).catch(() => setHealth(null));
    fetchRouterStatus().then(setRouterStatus).catch(() => setRouterStatus(null));
  }, []);

  return (
    <div>
      <PageHeader
        title="Settings"
        description="Environment configuration and system status. Runtime changes require editing .env and restarting the backend."
        action={
          <a
            href="http://localhost:8000/docs"
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-2 rounded-lg border border-slate-700 px-4 py-2 text-sm text-slate-300 hover:bg-slate-800"
          >
            <ExternalLink className="h-4 w-4" />
            API Docs
          </a>
        }
      />

      <div className="mb-8 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Backend Status"
          value={health?.status ?? 'offline'}
          subtext={health ? `${health.app_name} v${health.version}` : 'Start backend on port 8000'}
        />
        <StatCard label="Environment" value={health?.environment ?? '—'} subtext="APP_ENV" />
        <StatCard label="Router Type" value={routerStatus?.router_type ?? '—'} subtext="ROUTER_TYPE" />
        <StatCard
          label="Models Enabled"
          value={routerStatus ? `${routerStatus.enabled_models}/${routerStatus.total_models}` : '—'}
        />
      </div>

      {routerStatus && (
        <div className="mb-8 grid grid-cols-1 gap-6 lg:grid-cols-2">
          <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-6">
            <h3 className="text-sm font-medium text-white">Routing Policy</h3>
            <dl className="mt-4 space-y-2 text-sm">
              <div className="flex justify-between"><dt className="text-slate-400">Quality Floor</dt><dd className="text-white">{(routerStatus.quality_floor * 100).toFixed(0)}%</dd></div>
              <div className="flex justify-between"><dt className="text-slate-400">Cost Priority</dt><dd className="text-white">{routerStatus.cost_priority}</dd></div>
              <div className="flex justify-between"><dt className="text-slate-400">Latency Priority</dt><dd className="text-white">{routerStatus.latency_priority}</dd></div>
            </dl>
          </div>
          <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-6">
            <h3 className="text-sm font-medium text-white">Fallback Configuration</h3>
            <dl className="mt-4 space-y-2 text-sm">
              <div className="flex justify-between"><dt className="text-slate-400">Enabled</dt><dd className="text-white">{routerStatus.fallback_enabled ? 'Yes' : 'No'}</dd></div>
              <div className="flex justify-between"><dt className="text-slate-400">Max Attempts</dt><dd className="text-white">{routerStatus.max_fallback_attempts}</dd></div>
              <div className="flex justify-between"><dt className="text-slate-400">Quality Threshold</dt><dd className="text-white">{routerStatus.fallback_on_quality_below != null ? `${(routerStatus.fallback_on_quality_below * 100).toFixed(0)}%` : 'Disabled'}</dd></div>
              <div className="flex justify-between"><dt className="text-slate-400">Escalation</dt><dd className="text-white">{routerStatus.fallback_escalation}</dd></div>
            </dl>
          </div>
        </div>
      )}

      <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-6">
        <h3 className="text-sm font-medium text-white">Environment Variables</h3>
        <p className="mt-2 text-sm text-slate-400">
          Copy <code className="text-brand-100">.env.example</code> to <code className="text-brand-100">.env</code> and
          configure API keys for providers you want to use. Never commit real credentials.
        </p>
        <div className="mt-4 grid grid-cols-1 gap-6 md:grid-cols-2">
          <ul className="space-y-1 text-sm text-slate-500">
            <li>OPENAI_API_KEY — OpenAI models</li>
            <li>ANTHROPIC_API_KEY — Anthropic models</li>
            <li>GOOGLE_API_KEY — Google Gemini models</li>
            <li>ROUTER_TYPE — rule_based | tfidf | embedding | bert</li>
            <li>QUALITY_FLOOR — minimum acceptable quality (default 0.90)</li>
          </ul>
          <ul className="space-y-1 text-sm text-slate-500">
            <li>COST_PRIORITY / LATENCY_PRIORITY — routing optimization weights</li>
            <li>FALLBACK_ENABLED — retry with higher tier on provider errors</li>
            <li>MAX_FALLBACK_ATTEMPTS — max models to try (default 3)</li>
            <li>FALLBACK_ON_QUALITY_BELOW — escalate when judge score is low</li>
            <li>EVALUATE_ON_CHAT — post-response quality scoring</li>
            <li>ROUTER_API_KEY — optional bearer auth for /v1/* endpoints</li>
          </ul>
        </div>
      </div>

      <div className="mt-8 rounded-xl border border-slate-800 bg-slate-900/60 p-6">
        <h3 className="text-sm font-medium text-white">OpenAI-Compatible API</h3>
        <p className="mt-2 text-sm text-slate-400">
          Point any OpenAI SDK to <code className="text-brand-100">http://localhost:8000/v1</code> and use{' '}
          <code className="text-brand-100">model: &quot;auto&quot;</code> for adaptive routing.
        </p>
        <ul className="mt-3 space-y-1 text-sm text-slate-500">
          <li>POST /v1/chat/completions — OpenAI chat completions format</li>
          <li>GET /v1/models — list enabled models + auto</li>
          <li>X-Quality-Floor header — per-request quality override</li>
        </ul>
      </div>
    </div>
  );
}
