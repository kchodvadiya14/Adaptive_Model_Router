import type { ModelMetadata, ModelPerformance, ModelTier, UsageBreakdownEntry } from '../../types';

export interface PerformanceAggregates {
  requestCount: number;
  successRate: number | null;
  qualityFailureRate: number | null;
  fallbackRate: number | null;
  averageLatencyMs: number | null;
  totalEstimatedCost: number | null;
  averageEstimatedCost: number | null;
}

const TIER_ORDER: Record<string, number> = { small: 0, medium: 1, strong: 2 };

export function aggregatePerformance(models: ModelPerformance[]): PerformanceAggregates {
  const requestCount = models.reduce((sum, model) => sum + model.request_count, 0);
  const successCount = models.reduce((sum, model) => sum + model.success_count, 0);
  const qualityFailures = models.reduce((sum, model) => sum + model.outcomes.quality_failure, 0);

  let latencyWeighted = 0;
  let latencyWeight = 0;
  let costWeighted = 0;
  let costWeight = 0;
  let fallbackWeighted = 0;

  for (const model of models) {
    fallbackWeighted += model.fallback_rate * model.request_count;

    if (model.average_latency_ms != null && model.success_count > 0) {
      latencyWeighted += model.average_latency_ms * model.success_count;
      latencyWeight += model.success_count;
    }

    if (model.average_estimated_cost != null && model.success_count > 0) {
      costWeighted += model.average_estimated_cost * model.success_count;
      costWeight += model.success_count;
    }
  }

  return {
    requestCount,
    successRate: requestCount > 0 ? successCount / requestCount : null,
    qualityFailureRate: requestCount > 0 ? qualityFailures / requestCount : null,
    fallbackRate: requestCount > 0 ? fallbackWeighted / requestCount : null,
    averageLatencyMs: latencyWeight > 0 ? latencyWeighted / latencyWeight : null,
    totalEstimatedCost: costWeight > 0 ? costWeighted : null,
    averageEstimatedCost: costWeight > 0 ? costWeighted / costWeight : null,
  };
}

export function usageByTier(
  byModel: UsageBreakdownEntry[],
  models: ModelMetadata[],
): UsageBreakdownEntry[] {
  const tierById = new Map(models.map((model) => [model.id, model.tier]));
  const groups = new Map<string, UsageBreakdownEntry[]>();

  for (const entry of byModel) {
    const tier = tierById.get(entry.key) ?? 'unknown';
    const list = groups.get(tier) ?? [];
    list.push(entry);
    groups.set(tier, list);
  }

  return [...groups.entries()]
    .map(([key, entries]) => mergeUsageEntries(key, entries))
    .sort((a, b) => (TIER_ORDER[a.key] ?? 99) - (TIER_ORDER[b.key] ?? 99));
}

function mergeUsageEntries(key: string, entries: UsageBreakdownEntry[]): UsageBreakdownEntry {
  const totalRequests = entries.reduce((sum, entry) => sum + entry.total_requests, 0);
  const latencyWeighted = entries.reduce((sum, entry) => sum + entry.average_latency_ms * entry.total_requests, 0);

  return {
    key,
    total_requests: totalRequests,
    successful_requests: entries.reduce((sum, entry) => sum + entry.successful_requests, 0),
    fallback_requests: entries.reduce((sum, entry) => sum + entry.fallback_requests, 0),
    total_estimated_cost: entries.reduce((sum, entry) => sum + entry.total_estimated_cost, 0),
    average_latency_ms: totalRequests > 0 ? latencyWeighted / totalRequests : 0,
  };
}

export function lookupModel(id: string, models: ModelMetadata[]): ModelMetadata | undefined {
  return models.find((model) => model.id === id);
}

export function isModelTier(value: string): value is ModelTier {
  return value === 'small' || value === 'medium' || value === 'strong';
}
