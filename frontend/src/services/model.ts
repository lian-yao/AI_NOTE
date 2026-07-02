import request, { isNotFoundError } from '@/utils/request.ts'
import type { IProvider } from '@/types'
import {
  createLocalId,
  readLocalValue,
  skippedApiResult,
  writeLocalValue,
} from '@/services/fallback'

interface CallOpts {
  silent?: boolean
}

const cfg = (o?: CallOpts) => ({
  ...(o?.silent ? { suppressToast: true } : {}),
  suppressNotFoundToast: true,
})
const withParams = (opts: CallOpts | undefined, params: Record<string, unknown>) => ({
  ...cfg(opts),
  params,
})
const LOCAL_PROVIDERS_KEY = 'ai-note:providers:fallback'
const LOCAL_MODELS_KEY = 'ai-note:models:fallback'

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
    api_key: provider.api_key || (hasApiKey ? '******' : ''),
    base_url: provider.base_url || '',
    enabled: provider.enabled === false ? 0 : Number(provider.enabled ?? 1),
  }
}

function providerBody(data: ProviderPayload) {
  return {
    name: data.name,
    logo: data.logo,
    type: data.type === 'custom' ? 'openai-compatible' : data.type,
    base_url: data.base_url ?? data.baseUrl,
    api_key: data.api_key ?? data.apiKey,
    enabled: data.enabled == null ? undefined : Boolean(data.enabled),
  }
}

function getItems<T>(res: ModelListResponse<T> | ModelDataListResponse<T> | T[]): T[] {
  if (Array.isArray(res)) return res
  if ('items' in res && Array.isArray(res.items)) return res.items
  if ('data' in res && Array.isArray(res.data)) return res.data
  return []
}

function localModelId(): number {
  return Date.now() + Math.floor(Math.random() * 1000)
}

function readLocalProviders(): ProviderApiItem[] {
  return readLocalValue<ProviderApiItem[]>(LOCAL_PROVIDERS_KEY, [])
}

function writeLocalProviders(items: ProviderApiItem[]) {
  writeLocalValue(LOCAL_PROVIDERS_KEY, items)
}

function readLocalModels(): EnabledModelItem[] {
  return readLocalValue<EnabledModelItem[]>(LOCAL_MODELS_KEY, [])
}

function writeLocalModels(items: EnabledModelItem[]) {
  writeLocalValue(LOCAL_MODELS_KEY, items)
}

function localProviderFromPayload(data: ProviderPayload, current?: ProviderApiItem): ProviderApiItem {
  const apiKey = data.api_key ?? data.apiKey ?? current?.api_key ?? ''
  const baseUrl = data.base_url ?? data.baseUrl ?? current?.base_url ?? ''
  const type = data.type === 'custom' ? 'openai-compatible' : data.type || current?.type || 'openai-compatible'

  return {
    ...current,
    id: data.id || current?.id || createLocalId('provider'),
    name: data.name || current?.name || 'Custom Provider',
    logo: data.logo || current?.logo || 'custom',
    type,
    base_url: baseUrl,
    api_key: apiKey,
    has_api_key: Boolean(apiKey || current?.has_api_key),
    enabled: data.enabled == null ? current?.enabled ?? true : Boolean(data.enabled),
    created_at: current?.created_at || new Date().toISOString(),
    updated_at: new Date().toISOString(),
  }
}

function upsertLocalProvider(data: ProviderPayload): string {
  const providers = readLocalProviders()
  const index = providers.findIndex(provider => provider.id === data.id)
  const item = localProviderFromPayload(data, index >= 0 ? providers[index] : undefined)
  const next = index >= 0
    ? providers.map(provider => (provider.id === item.id ? item : provider))
    : [...providers, item]

  writeLocalProviders(next)
  return item.id
}

function deleteLocalProvider(id: string) {
  writeLocalProviders(readLocalProviders().filter(provider => provider.id !== id))
  writeLocalModels(readLocalModels().filter(model => model.provider_id !== id))
}

function addLocalModel(data: { provider_id: string; model_name: string }): EnabledModelItem {
  const models = readLocalModels()
  const existing = models.find(
    model => model.provider_id === data.provider_id && model.model_name === data.model_name,
  )
  if (existing) return existing

  const item: EnabledModelItem = {
    id: localModelId(),
    provider_id: data.provider_id,
    model_name: data.model_name,
    enabled: true,
    created_at: new Date().toISOString(),
  }
  writeLocalModels([...models, item])
  return item
}

function deleteLocalModel(modelId: number) {
  writeLocalModels(readLocalModels().filter(model => Number(model.id) !== modelId))
}

export const getProviderList = async (opts?: CallOpts) => {
  try {
    const res = await request.get<unknown, ModelListResponse<ProviderApiItem> | ModelDataListResponse<ProviderApiItem>>(
      '/providers',
      cfg(opts),
    )
    return getItems(res).map(normalizeProvider)
  } catch (error) {
    if (isNotFoundError(error)) return readLocalProviders().map(normalizeProvider)
    throw error
  }
}

export const getProviderById = async (id: string, opts?: CallOpts) => {
  try {
    const res = await request.get<unknown, ProviderApiItem>(
      `/providers/${encodeURIComponent(id)}`,
      cfg(opts),
    )
    return normalizeProvider(res)
  } catch (error) {
    const localProvider = readLocalProviders().find(provider => provider.id === id)
    if (isNotFoundError(error) && localProvider) return normalizeProvider(localProvider)
    throw error
  }
}

export const updateProviderById = async (data: ProviderPayload, opts?: CallOpts) => {
  if (!data.id) throw new Error('provider id is required')

  try {
    return await request.put(
      `/providers/${encodeURIComponent(data.id)}`,
      providerBody(data),
      cfg(opts),
    )
  } catch (error) {
    if (isNotFoundError(error)) return upsertLocalProvider(data)
    throw error
  }
}

export const addProvider = async (data: ProviderPayload, opts?: CallOpts): Promise<string> => {
  try {
    const res = await request.post<unknown, { id: string }>('/providers', providerBody(data), cfg(opts))
    return res.id
  } catch (error) {
    if (isNotFoundError(error)) return upsertLocalProvider(data)
    throw error
  }
}

export const deleteProviderById = async (id: string, opts?: CallOpts) => {
  try {
    return await request.delete(`/providers/${encodeURIComponent(id)}`, cfg(opts))
  } catch (error) {
    if (isNotFoundError(error)) return deleteLocalProvider(id)
    throw error
  }
}

export const testConnection = async (data: TestConnectionPayload, opts?: CallOpts) => {
  try {
    return await request.post(
      `/providers/${encodeURIComponent(data.id)}/test`,
      { model_name: data.model },
      cfg(opts),
    )
  } catch (error) {
    if (isNotFoundError(error)) return skippedApiResult()
    throw error
  }
}

export const fetchModels = async (providerId: string, opts?: CallOpts) => {
  try {
    return await request.get<unknown, RemoteModelsResponse>(
      `/providers/${encodeURIComponent(providerId)}/remote-models`,
      cfg(opts),
    )
  } catch (error) {
    if (isNotFoundError(error)) {
      const data = readLocalModels()
        .filter(model => model.provider_id === providerId)
        .map(model => ({ id: model.model_name, model_name: model.model_name }))
      return { data }
    }
    throw error
  }
}

export const fetchEnableModelById = async (id: string, opts?: CallOpts) => {
  try {
    const res = await request.get<
      unknown,
      ModelListResponse<EnabledModelItem> | ModelDataListResponse<EnabledModelItem>
    >(
      '/models',
      withParams(opts, { provider_id: id, enabled: true }),
    )
    return getItems(res)
  } catch (error) {
    if (isNotFoundError(error)) {
      return readLocalModels().filter(model => model.provider_id === id)
    }
    throw error
  }
}

export async function addModel(
  data: { provider_id: string; model_name: string },
  opts?: CallOpts,
) {
  try {
    return await request.post('/models', data, cfg(opts))
  } catch (error) {
    if (isNotFoundError(error)) return addLocalModel(data)
    throw error
  }
}

export const fetchEnableModels = async (opts?: CallOpts) => {
  try {
    const res = await request.get<
      unknown,
      ModelListResponse<EnabledModelItem> | ModelDataListResponse<EnabledModelItem>
    >(
      '/models',
      withParams(opts, { enabled: true }),
    )
    return getItems(res)
  } catch (error) {
    if (isNotFoundError(error)) return readLocalModels()
    throw error
  }
}

export const deleteModelById = async (modelId: number, opts?: CallOpts) => {
  try {
    return await request.delete(`/models/${modelId}`, cfg(opts))
  } catch (error) {
    if (isNotFoundError(error)) return deleteLocalModel(modelId)
    throw error
  }
}
