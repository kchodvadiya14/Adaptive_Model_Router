import axios from 'axios';
import type {
  BenchmarkJobStatus,
  BenchmarkReport,
  BenchmarkStrategy,
  ChatRequest,
  ChatResponse,
  DatasetGenerateJobStatus,
  DatasetManifest,
  DatasetRecordsResponse,
  EvaluateResponse,
  HealthResponse,
  MetricsSummary,
  ModelCreateRequest,
  ModelMetadata,
  ModelUpdateRequest,
  PreferenceRecord,
  RouteConfigOverride,
  RoutingDecision,
  RouterStatusResponse,
  TrainedModelInfo,
  TrainingJobStatus,
  ExperimentJobStatus,
  ExperimentManifest,
  ExperimentReport,
} from '../types';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '',
  headers: { 'Content-Type': 'application/json' },
});

export async function fetchHealth(): Promise<HealthResponse> {
  const { data } = await api.get<HealthResponse>('/health');
  return data;
}

export async function fetchModels(enabledOnly = false): Promise<ModelMetadata[]> {
  const { data } = await api.get<ModelMetadata[]>('/api/models', {
    params: { enabled_only: enabledOnly },
  });
  return data;
}

export async function fetchModel(id: string): Promise<ModelMetadata> {
  const { data } = await api.get<ModelMetadata>(`/api/models/${id}`);
  return data;
}

export async function createModel(payload: ModelCreateRequest): Promise<ModelMetadata> {
  const { data } = await api.post<ModelMetadata>('/api/models', payload);
  return data;
}

export async function updateModel(id: string, payload: ModelUpdateRequest): Promise<ModelMetadata> {
  const { data } = await api.patch<ModelMetadata>(`/api/models/${id}`, payload);
  return data;
}

export async function enableModel(id: string): Promise<ModelMetadata> {
  const { data } = await api.post<ModelMetadata>(`/api/models/${id}/enable`);
  return data;
}

export async function disableModel(id: string): Promise<ModelMetadata> {
  const { data } = await api.post<ModelMetadata>(`/api/models/${id}/disable`);
  return data;
}

export async function fetchRouterStatus(): Promise<RouterStatusResponse> {
  const { data } = await api.get<RouterStatusResponse>('/api/router/status');
  return data;
}

export async function sendChat(request: ChatRequest): Promise<ChatResponse> {
  const { data } = await api.post<ChatResponse>('/api/chat', request);
  return data;
}

export async function routePrompt(
  prompt: string,
  configuration?: RouteConfigOverride,
): Promise<RoutingDecision> {
  const { data } = await api.post<RoutingDecision>('/api/route', {
    prompt,
    configuration,
  });
  return data;
}

export async function evaluateResponse(prompt: string, response: string): Promise<EvaluateResponse> {
  const { data } = await api.post<EvaluateResponse>('/api/evaluate', { prompt, response });
  return data;
}

export async function fetchMetrics(): Promise<MetricsSummary> {
  const { data } = await api.get<MetricsSummary>('/api/metrics');
  return data;
}

export async function startBenchmark(payload: {
  dataset_path?: string;
  quality_floor?: number;
  max_prompts?: number;
  strategies?: BenchmarkStrategy[];
}): Promise<BenchmarkJobStatus> {
  const { data } = await api.post<BenchmarkJobStatus>('/api/benchmark', payload);
  return data;
}

export async function fetchBenchmarkStatus(jobId: string): Promise<BenchmarkJobStatus> {
  const { data } = await api.get<BenchmarkJobStatus>(`/api/benchmark/status/${jobId}`);
  return data;
}

export async function fetchBenchmarks(): Promise<BenchmarkReport[]> {
  const { data } = await api.get<BenchmarkReport[]>('/api/benchmarks');
  return data;
}

export async function fetchBenchmarkReport(reportId: string): Promise<BenchmarkReport> {
  const { data } = await api.get<BenchmarkReport>(`/api/benchmarks/${reportId}`);
  return data;
}

export async function fetchDatasets(): Promise<DatasetManifest[]> {
  const { data } = await api.get<DatasetManifest[]>('/api/dataset');
  return data;
}

export async function startDatasetGeneration(payload: {
  source_path?: string;
  name?: string;
  quality_floor?: number;
  max_prompts?: number;
  description?: string;
}): Promise<DatasetGenerateJobStatus> {
  const { data } = await api.post<DatasetGenerateJobStatus>('/api/dataset/generate', payload);
  return data;
}

export async function fetchDatasetGenerationStatus(jobId: string): Promise<DatasetGenerateJobStatus> {
  const { data } = await api.get<DatasetGenerateJobStatus>(`/api/dataset/generate/status/${jobId}`);
  return data;
}

export async function fetchDatasetRecords(
  datasetId: string,
  params?: { offset?: number; limit?: number },
): Promise<DatasetRecordsResponse> {
  const { data } = await api.get<DatasetRecordsResponse>(`/api/dataset/${datasetId}`, { params });
  return data;
}

export async function submitHumanEval(
  datasetId: string,
  payload: {
    record_id: string;
    small_score?: number;
    medium_score?: number;
    strong_score?: number;
    preferred_model?: 'small' | 'medium' | 'strong';
    notes?: string;
  },
): Promise<PreferenceRecord> {
  const { data } = await api.post<PreferenceRecord>(`/api/dataset/${datasetId}/human-eval`, payload);
  return data;
}

export async function startTraining(payload: {
  dataset_id: string;
  router_type: 'tfidf' | 'embedding' | 'bert';
  routing_threshold?: number;
}): Promise<TrainingJobStatus> {
  const { data } = await api.post<TrainingJobStatus>('/api/training/start', payload);
  return data;
}

export async function fetchTrainingStatus(jobId: string): Promise<TrainingJobStatus> {
  const { data } = await api.get<TrainingJobStatus>(`/api/training/status/${jobId}`);
  return data;
}

export async function fetchTrainedModels(): Promise<TrainedModelInfo[]> {
  const { data } = await api.get<TrainedModelInfo[]>('/api/training/models');
  return data;
}

export async function startExperiment(payload: {
  experiment_type?: string;
  name?: string;
  dataset_path?: string;
  quality_floor?: number;
  max_prompts?: number;
  quality_floors?: number[];
  router_types?: string[];
}): Promise<ExperimentJobStatus> {
  const { data } = await api.post<ExperimentJobStatus>('/api/experiments/run', payload);
  return data;
}

export async function fetchExperimentStatus(jobId: string): Promise<ExperimentJobStatus> {
  const { data } = await api.get<ExperimentJobStatus>(`/api/experiments/status/${jobId}`);
  return data;
}

export async function fetchExperiments(): Promise<ExperimentManifest[]> {
  const { data } = await api.get<ExperimentManifest[]>('/api/experiments');
  return data;
}

export async function fetchExperimentReport(reportId: string): Promise<ExperimentReport> {
  const { data } = await api.get<ExperimentReport>(`/api/experiments/${reportId}`);
  return data;
}

export { api };
