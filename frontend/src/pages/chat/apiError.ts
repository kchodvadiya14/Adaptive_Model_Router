import axios from 'axios';

export interface ParsedApiError {
  message: string;
  isTimeout: boolean;
}

function detailMessage(detail: unknown): string | null {
  if (typeof detail === 'string' && detail.trim()) return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] as { msg?: string; message?: string };
    return first?.msg || first?.message || null;
  }
  if (detail && typeof detail === 'object') {
    const record = detail as { message?: unknown; error?: unknown; detail?: unknown };
    if (typeof record.message === 'string' && record.message.trim()) return record.message;
    if (typeof record.detail === 'string' && record.detail.trim()) return record.detail;
    if (typeof record.error === 'string' && record.error.trim()) return record.error;
  }
  return null;
}

function isTimeoutDetail(detail: unknown, status?: number): boolean {
  if (status === 504) return true;
  if (detail && typeof detail === 'object' && 'error' in detail) {
    return (detail as { error?: unknown }).error === 'request_timeout';
  }
  return false;
}

export function parseApiError(err: unknown, fallback: string): ParsedApiError {
  if (axios.isAxiosError(err)) {
    const status = err.response?.status;
    const detail = err.response?.data?.detail ?? err.response?.data;
    const isTimeout = isTimeoutDetail(detail, status) || err.code === 'ECONNABORTED';
    const fromDetail = detailMessage(detail);
    if (isTimeout) {
      return {
        message: fromDetail || 'The request timed out before a model response was returned.',
        isTimeout: true,
      };
    }
    return { message: fromDetail || err.message || fallback, isTimeout: false };
  }
  return { message: fallback, isTimeout: false };
}
