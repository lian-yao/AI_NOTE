const API_PREFIX = '/api/v1'
const DEFAULT_TAURI_BACKEND_BASE_URL = 'http://127.0.0.1:8483'

export function normalizeApiBaseURL(rawBaseURL?: string): string {
  const baseURL = (rawBaseURL || '').trim().replace(/\/+$/, '')

  if (!baseURL) return API_PREFIX
  if (/\/api\/v1$/i.test(baseURL)) return baseURL
  if (/\/api$/i.test(baseURL)) return `${baseURL}/v1`

  return `${baseURL}${API_PREFIX}`
}

export function getApiBaseURL(): string {
  const envBaseURL = import.meta.env.VITE_API_BASE_URL
  if (envBaseURL) return normalizeApiBaseURL(envBaseURL)

  if (typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window) {
    return normalizeApiBaseURL(
      import.meta.env.VITE_TAURI_BACKEND_BASE_URL || DEFAULT_TAURI_BACKEND_BASE_URL,
    )
  }

  return normalizeApiBaseURL()
}
