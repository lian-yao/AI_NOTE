export interface SkippedApiResult {
  skipped: true
  reason: 'api-not-implemented'
}

export function skippedApiResult(): SkippedApiResult {
  return {
    skipped: true,
    reason: 'api-not-implemented',
  }
}

export function isSkippedApiResult(value: unknown): value is SkippedApiResult {
  return (
    Boolean(value) &&
    typeof value === 'object' &&
    (value as Partial<SkippedApiResult>).skipped === true &&
    (value as Partial<SkippedApiResult>).reason === 'api-not-implemented'
  )
}

export function readLocalValue<T>(key: string, fallback: T): T {
  if (typeof window === 'undefined') return fallback

  try {
    const raw = window.localStorage.getItem(key)
    return raw ? (JSON.parse(raw) as T) : fallback
  } catch {
    return fallback
  }
}

export function writeLocalValue<T>(key: string, value: T): void {
  if (typeof window === 'undefined') return

  try {
    window.localStorage.setItem(key, JSON.stringify(value))
  } catch {
    // Local persistence is a best-effort fallback for APIs that are not ready yet.
  }
}

export function createLocalId(prefix: string): string {
  const randomId =
    typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(16).slice(2)}`

  return `${prefix}_${randomId}`
}
