export type ModelTier = 'small' | 'medium' | 'strong';
export type ModelType = 'api' | 'open_source' | 'local';

export interface ModelMetadata {
  id: string;
  name: string;
  provider: string;
  type: ModelType;
  tier: ModelTier;
  input_cost_per_1m_tokens: number;
  output_cost_per_1m_tokens: number;
  context_window: number;
  capabilities: string[];
  supports_vision: boolean;
  supports_tools: boolean;
  enabled: boolean;
  avg_latency_ms: number;
  quality_score: number;
}

export interface HealthResponse {
  status: 'ok' | 'degraded' | 'error';
  app_name: string;
  version: string;
  environment: string;
}

export interface ChatMessage {
  role: 'system' | 'user' | 'assistant';
  content: string;
  has_image?: boolean;
}

export interface ChatRequest {
  model: string;
  messages: ChatMessage[];
  max_tokens?: number;
  temperature?: number;
  quality_floor?: number;
  tools?: Array<Record<string, unknown>>;
  request_id?: string;
  user_id?: string;
  session_id?: string;
  tags?: Record<string, string>;
  preferred_model?: string;
  max_cost?: number;
  max_latency_ms?: number;
  timeout_ms?: number;
}

export interface RouteConfigOverride {
  quality_floor?: number;
  cost_priority?: number;
  latency_priority?: number;
}

export interface JudgeScore {
  correctness: number;
  relevance: number;
  completeness: number;
  reasoning_quality: number;
  instruction_following: number;
  overall: number;
  judge_provider: string;
  judge_reasoning: string;
}

export interface EvaluateResponse {
  scores: JudgeScore;
}

export interface ModelCreateRequest {
  id: string;
  name: string;
  provider: string;
  type?: ModelType;
  tier: ModelTier;
  input_cost_per_1m_tokens: number;
  output_cost_per_1m_tokens: number;
  context_window: number;
  capabilities?: string[];
  supports_vision?: boolean;
  supports_tools?: boolean;
  enabled?: boolean;
  avg_latency_ms?: number;
  quality_score?: number;
}

export interface ModelUpdateRequest {
  name?: string;
  provider?: string;
  type?: ModelType;
  tier?: ModelTier;
  input_cost_per_1m_tokens?: number;
  output_cost_per_1m_tokens?: number;
  context_window?: number;
  capabilities?: string[];
  supports_vision?: boolean;
  supports_tools?: boolean;
  enabled?: boolean;
  avg_latency_ms?: number;
  quality_score?: number;
}

export interface TokenUsage {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
}

export interface CostBreakdown {
  input_cost: number;
  output_cost: number;
  total_cost: number;
}

export interface RoutingDecision {
  selected_model: string;
  model_tier: ModelTier;
  confidence: number;
  difficulty: number;
  task_type: string;
  reason: string;
  estimated_cost: number;
  estimated_quality: number;
  strong_model_baseline_cost: number;
  cost_saved_vs_strong: number;
  explanation: string[];
  tier_qualities: Array<{
    tier: string;
    model_id: string | null;
    expected_quality: number;
    estimated_cost: number;
    meets_quality_floor: boolean;
  }>;
  features: Record<string, unknown>;
  preferred_model?: string | null;
  preferred_model_honored?: boolean | null;
}

export interface FallbackAttemptRecord {
  model_id: string;
  model_tier: string;
  success: boolean;
  reason?: string | null;
  latency_ms?: number | null;
}

export interface FallbackInfo {
  used: boolean;
  original_model: string;
  final_model: string;
  attempts: FallbackAttemptRecord[];
  escalation_reason?: string | null;
}

export interface ChatResponse {
  content: string;
  model: string;
  model_name: string;
  provider: string;
  tier: ModelTier;
  usage: TokenUsage;
  cost: CostBreakdown;
  latency_ms: number;
  routed: boolean;
  routing: RoutingDecision | null;
  fallback: FallbackInfo | null;
  request_id?: string | null;
}

export interface MetricsSummary {
  total_requests: number;
  total_cost: number;
  average_cost: number;
  average_quality: number | null;
  quality_retention: number | null;
  cost_saved: number;
  average_latency_ms: number;
  strong_model_usage: number;
  fallback_rate: number;
  requests_by_model: Record<string, number>;
  requests_by_task: Record<string, number>;
  requests_by_tier: Record<string, number>;
}

export interface AggregateMetrics {
  total_requests: number;
  average_quality: number;
  average_cost: number;
  total_cost: number;
  cost_reduction: number;
  quality_retention: number;
  routing_accuracy: number;
  strong_model_usage: number;
  average_latency_ms: number;
  p50_latency_ms: number;
  p95_latency_ms: number;
}

export interface BenchmarkReport {
  id: string;
  dataset_path: string;
  quality_floor: number;
  created_at: string;
  strategies: Array<{
    strategy: string;
    metrics: AggregateMetrics;
    samples?: Array<Record<string, unknown>>;
  }>;
}

export type BenchmarkStrategy = 'always_strong' | 'always_cheap' | 'adaptive_router';

export interface BenchmarkJobStatus {
  job_id: string;
  status: 'queued' | 'running' | 'completed' | 'failed';
  progress: number;
  error?: string | null;
  report?: BenchmarkReport | null;
}

export interface DatasetManifest {
  id: string;
  name: string;
  created_at: string;
  source_path: string;
  output_path: string;
  quality_floor: number;
  record_count: number;
  judge_provider: string;
  description: string;
}

export interface PreferenceRecord {
  id: string;
  prompt: string;
  task_type: string;
  difficulty: number;
  small_model_id?: string;
  medium_model_id?: string;
  strong_model_id?: string;
  small_response?: string;
  medium_response?: string;
  strong_response?: string;
  small_score: number;
  medium_score: number;
  strong_score: number;
  preferred_model: 'small' | 'medium' | 'strong';
  small_sufficient: boolean;
  medium_sufficient: boolean;
  strong_sufficient: boolean;
  quality_floor: number;
  evaluation_source: string;
  human_notes?: string | null;
}

export interface DatasetGenerateJobStatus {
  job_id: string;
  status: 'queued' | 'running' | 'completed' | 'failed';
  progress: number;
  error?: string | null;
  manifest?: DatasetManifest | null;
}

export interface DatasetRecordsResponse {
  manifest: DatasetManifest;
  records: PreferenceRecord[];
  total: number;
  offset: number;
  limit: number;
}

export interface TrainedModelInfo {
  id: string;
  router_type: 'tfidf' | 'embedding' | 'bert';
  dataset_id: string;
  model_path: string;
  created_at: string;
  metrics: {
    train_accuracy: number;
    validation_accuracy: number;
    test_accuracy: number;
    precision: number;
    recall: number;
    f1: number;
    routing_threshold: number;
    probability_mean?: number | null;
    confusion_matrix: {
      true_negative: number;
      false_positive: number;
      false_negative: number;
      true_positive: number;
    };
  };
  threshold: number;
  samples: number;
}

export interface TrainingJobStatus {
  job_id: string;
  status: 'queued' | 'running' | 'completed' | 'failed';
  progress: number;
  error?: string | null;
  result?: TrainedModelInfo | null;
}

export interface RouterStatusResponse {
  router_type: string;
  quality_floor: number;
  cost_priority: number;
  latency_priority: number;
  fallback_enabled: boolean;
  max_fallback_attempts: number;
  fallback_on_quality_below: number | null;
  fallback_escalation: string;
  enabled_models: number;
  total_models: number;
  routing_threshold: number;
  judge_provider: string;
  judge_model_id: string;
  evaluate_on_chat: boolean;
  health_failure_threshold: number;
  health_cooldown_seconds: number;
  auth_enabled: boolean;
  configured_providers: Record<string, boolean>;
}

export interface ExperimentVariant {
  name: string;
  description: string;
  metrics: AggregateMetrics;
  config: Record<string, unknown>;
}

export interface ExperimentSection {
  name: string;
  experiment_type: string;
  variants: ExperimentVariant[];
}

export interface ExperimentReport {
  id: string;
  name: string;
  experiment_type: string;
  dataset_path: string;
  created_at: string;
  sections: ExperimentSection[];
  summary: string;
  markdown_summary: string;
}

export interface ExperimentJobStatus {
  job_id: string;
  status: 'queued' | 'running' | 'completed' | 'failed';
  progress: number;
  error?: string | null;
  report?: ExperimentReport | null;
}

export interface ExperimentManifest {
  id: string;
  name: string;
  experiment_type: string;
  created_at: string;
  dataset_path: string;
}

export type CircuitState = 'closed' | 'open' | 'half_open';

export interface ModelHealthStatus {
  model_id: string;
  provider: string;
  state: CircuitState;
  consecutive_failures: number;
  recent_failures: number;
  recent_successes: number;
  opened_at?: string | null;
  last_success?: string | null;
  last_failure?: string | null;
  last_error?: string | null;
  cooldown_remaining_seconds?: number | null;
}

export interface OutcomeCounts {
  success: number;
  quality_failure: number;
  retryable_failure: number;
  non_retryable_failure: number;
  timeout: number;
}

export interface ModelPerformance {
  model_id: string;
  provider: string;
  request_count: number;
  success_count: number;
  success_rate: number;
  quality_failure_rate: number;
  fallback_rate: number;
  average_latency_ms: number | null;
  average_estimated_cost: number | null;
  average_quality_score: number | null;
  outcomes: OutcomeCounts;
  first_seen: string;
  last_seen: string;
}

export interface PerformanceFilters {
  model_id?: string | null;
  task_type?: string | null;
  since?: string | null;
  until?: string | null;
}

export interface PerformanceReport {
  filters: PerformanceFilters;
  models: ModelPerformance[];
}

export interface UsageFilters {
  user_id?: string | null;
  session_id?: string | null;
  model_id?: string | null;
  tag_key?: string | null;
  tag_value?: string | null;
}

export interface UsageBreakdownEntry {
  key: string;
  total_requests: number;
  successful_requests: number;
  fallback_requests: number;
  total_estimated_cost: number;
  average_latency_ms: number;
}

export interface UsageSummary {
  filters: UsageFilters;
  total_requests: number;
  successful_requests: number;
  fallback_requests: number;
  total_estimated_cost: number;
  average_latency_ms: number;
  by_user: UsageBreakdownEntry[];
  by_model: UsageBreakdownEntry[];
  by_tag: UsageBreakdownEntry[];
}
