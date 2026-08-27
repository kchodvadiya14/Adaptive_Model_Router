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
}

export interface ChatRequest {
  model: string;
  messages: ChatMessage[];
  max_tokens?: number;
  temperature?: number;
  quality_floor?: number;
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
