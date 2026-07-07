import request from '@/utils/request.ts'
import type { IProvider } from '@/types'

interface CallOpts {
  silent?: boolean
}

const cfg = (opts?: CallOpts) => ({
  ...(opts?.silent ? { suppressToast: true } : {}),
  suppressNotFoundToast: true,
})

const withParams = (opts: CallOpts | undefined, params: Record<string, unknown>) => ({
  ...cfg(opts),
  params,
})

export type ProviderPayload = Partial<
  Pick<IProvider, 'id' | 'name' | 'logo' | 'type' | 'enabled'>
> & {
  api_key?: string
  apiKey?: string
  base_url?: string
  baseUrl?: string
}

export interface TestConnectionPayload {
  id: string
  model: string
}

interface ProviderApiItem {
  id: string
  name: string
  logo?: string
  type?: string
  base_url?: string
  enabled?: boolean | number
  has_api_key?: boolean
  api_key?: string
  created_at?: string
  updated_at?: string
}

interface ModelListResponse<T> {
  items: T[]
}

interface ModelDataListResponse<T> {
  data: T[]
}

interface RemoteModelsResponse {
  models?: unknown[] | { data?: unknown[] }
  data?: unknown[]
}

interface EnabledModelItem {
  id: string | number
  provider_id: string
  model_name: string
  enabled?: boolean
  created_at?: string
}

function normalizeProvider(provider: ProviderApiItem) {
  const hasApiKey = Boolean(provider.has_api_key)
  return {
    ...provider,
    logo: provider.logo || 'custom',
    type: provider.type || 'openai-compatible',
    api_key: provider.api_key || '',
    has_api_key: hasApiKey,
    base_url: provider.base_url || '',
    enabled: provider.enabled === false ? 0 : Number(provider.enabled ?? 1),
  }
}

function providerBody(data: ProviderPayload) {
  const apiKey = data.api_key ?? data.apiKey
  const body: Record<string, unknown> = {
    name: data.name,
    logo: data.logo,
    type: data.type === 'custom' ? 'openai-compatible' : data.type,
    base_url: data.base_url ?? data.baseUrl,
    enabled: data.enabled == null ? undefined : Boolean(data.enabled),
  }
  if (apiKey !== undefined) {
    body.api_key = apiKey
  }
  return body
}

function getItems<T>(res: ModelListResponse<T> | ModelDataListResponse<T> | T[]): T[] {
  if (Array.isArray(res)) return res
  if ('items' in res && Array.isArray(res.items)) return res.items
  if ('data' in res && Array.isArray(res.data)) return res.data
  return []
}

export const getProviderList = async (opts?: CallOpts) => {
  const res = await request.get<
    unknown,
    ModelListResponse<ProviderApiItem> | ModelDataListResponse<ProviderApiItem>
  >('/providers', cfg(opts))
  return getItems(res).map(normalizeProvider)
}

export const getProviderById = async (id: string, opts?: CallOpts) => {
  const res = await request.get<unknown, ProviderApiItem>(
    `/providers/${encodeURIComponent(id)}`,
    cfg(opts),
  )
  return normalizeProvider(res)
}

export const updateProviderById = async (data: ProviderPayload, opts?: CallOpts) => {
  if (!data.id) throw new Error('provider id is required')

  return await request.put(
    `/providers/${encodeURIComponent(data.id)}`,
    providerBody(data),
    cfg(opts),
  )
}

export const addProvider = async (data: ProviderPayload, opts?: CallOpts): Promise<string> => {
  const res = await request.post<unknown, { id: string }>('/providers', providerBody(data), cfg(opts))
  return res.id
}

export const deleteProviderById = async (id: string, opts?: CallOpts) => {
  return await request.delete(`/providers/${encodeURIComponent(id)}`, cfg(opts))
}

export const testConnection = async (data: TestConnectionPayload, opts?: CallOpts) => {
  return await request.post(
    `/providers/${encodeURIComponent(data.id)}/test`,
    { model_name: data.model },
    cfg(opts),
  )
}

export const fetchModels = async (providerId: string, opts?: CallOpts) => {
  return await request.get<unknown, RemoteModelsResponse>(
    `/providers/${encodeURIComponent(providerId)}/remote-models`,
    cfg(opts),
  )
}

export const fetchEnableModelById = async (id: string, opts?: CallOpts) => {
  const res = await request.get<
    unknown,
    ModelListResponse<EnabledModelItem> | ModelDataListResponse<EnabledModelItem>
  >('/models', withParams(opts, { provider_id: id, enabled: true }))
  return getItems(res)
}

export const fetchProviderModelRowsById = async (id: string, opts?: CallOpts) => {
  const res = await request.get<
    unknown,
    ModelListResponse<EnabledModelItem> | ModelDataListResponse<EnabledModelItem>
  >('/models', withParams(opts, { provider_id: id, include_disabled: true }))
  return getItems(res)
}

export async function addModel(
  data: { provider_id: string; model_name: string },
  opts?: CallOpts,
) {
  return await request.post('/models', data, cfg(opts))
}

export const fetchEnableModels = async (opts?: CallOpts) => {
  const res = await request.get<
    unknown,
    ModelListResponse<EnabledModelItem> | ModelDataListResponse<EnabledModelItem>
  >('/models', withParams(opts, { enabled: true }))
  return getItems(res)
}

export const deleteModelById = async (modelId: number, opts?: CallOpts) => {
  return await request.delete(`/models/${modelId}`, cfg(opts))
}
