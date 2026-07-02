const API_PREFIX = '/api/v1'

export function normalizeApiBaseURL(rawBaseURL?: string): string {
  const baseURL = (rawBaseURL || '').trim().replace(/\/+$/, '')

  if (!baseURL) return API_PREFIX
  if (/\/api\/v1$/i.test(baseURL)) return baseURL
  if (/\/api$/i.test(baseURL)) return `${baseURL}/v1`

  return `${baseURL}${API_PREFIX}`
}

export function getApiBaseURL(): string {
  return normalizeApiBaseURL(import.meta.env.VITE_API_BASE_URL)
}
