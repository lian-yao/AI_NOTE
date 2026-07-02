import request, { isNotFoundError } from '@/utils/request'
import {
  readLocalValue,
  skippedApiResult,
  writeLocalValue,
} from '@/services/fallback'
import { getSystemConfig, updateSystemConfig } from '@/services/system'

interface CallOpts {
  silent?: boolean
}

const cfg = (opts?: CallOpts) => ({
  ...(opts?.silent ? { suppressToast: true } : {}),
  suppressNotFoundToast: true,
})
const LOCAL_TRANSCRIBER_CONFIG_KEY = 'ai-note:transcriber-config:fallback'
const LOCAL_WHISPER_MODELS_KEY = 'ai-note:whisper-models:fallback'

export interface TranscriberConfig {
  transcriber_type: string
  whisper_model_size: string
  available_types: { value: string; label: string }[]
  whisper_model_sizes: string[]
  whisper_builtin_models?: Record<string, string>
  whisper_custom_models?: Record<string, string>
  mlx_whisper_available: boolean
}

export interface ModelStatus {
  model_size: string
  downloaded: boolean
  downloading: boolean
  failed?: boolean
  error?: string | null
}

export interface ModelsStatusResponse {
  whisper: ModelStatus[]
  mlx_whisper: ModelStatus[]
  mlx_available: boolean
}

const defaultTranscriberConfig: TranscriberConfig = {
  transcriber_type: 'fast-whisper',
  whisper_model_size: 'base',
  available_types: [
    { value: 'fast-whisper', label: 'fast-whisper' },
    { value: 'mlx-whisper', label: 'mlx-whisper' },
    { value: 'groq', label: 'Groq' },
    { value: 'bcut', label: '必剪' },
  ],
  whisper_model_sizes: ['tiny', 'base', 'small', 'medium', 'large-v3'],
  mlx_whisper_available: false,
}

const defaultWhisperModels: WhisperModelsResponse = {
  builtin: {
    tiny: 'tiny',
    base: 'base',
    small: 'small',
    medium: 'medium',
    'large-v3': 'large-v3',
  },
  custom: {},
}

function readLocalTranscriberConfig(): TranscriberConfig {
  return readLocalValue<TranscriberConfig>(
    LOCAL_TRANSCRIBER_CONFIG_KEY,
    defaultTranscriberConfig,
  )
}

async function readSystemTranscriberConfig(opts?: CallOpts): Promise<TranscriberConfig> {
  const systemConfig = await getSystemConfig(opts)
  return {
    ...readLocalTranscriberConfig(),
    transcriber_type: systemConfig.transcriber_mode || defaultTranscriberConfig.transcriber_type,
    whisper_model_size: systemConfig.whisper_model_size || defaultTranscriberConfig.whisper_model_size,
  }
}

function writeLocalTranscriberConfig(data: Partial<TranscriberConfig>) {
  writeLocalValue(LOCAL_TRANSCRIBER_CONFIG_KEY, {
    ...readLocalTranscriberConfig(),
    ...data,
  })
}

function localModelsStatus(): ModelsStatusResponse {
  const config = readLocalTranscriberConfig()
  return {
    whisper: config.whisper_model_sizes.map(model_size => ({
      model_size,
      downloaded: model_size === config.whisper_model_size,
      downloading: false,
    })),
    mlx_whisper: [],
    mlx_available: Boolean(config.mlx_whisper_available),
  }
}

export const getTranscriberConfig = async (opts?: CallOpts): Promise<TranscriberConfig> => {
  try {
    return await request.get('/transcribers/config', cfg(opts))
  } catch (error) {
    if (isNotFoundError(error)) {
      return await readSystemTranscriberConfig(opts).catch(() => readLocalTranscriberConfig())
    }
    throw error
  }
}

export const updateTranscriberConfig = async (data: {
  transcriber_type: string
  whisper_model_size?: string
}) => {
  try {
    return await request.put('/transcribers/config', data, cfg())
  } catch (error) {
    if (isNotFoundError(error)) {
      await updateSystemConfig({
        transcriber_mode: data.transcriber_type,
        whisper_model_size: data.whisper_model_size,
      }).catch(() => undefined)
      writeLocalTranscriberConfig(data)
      return readLocalTranscriberConfig()
    }
    throw error
  }
}

export const getModelsStatus = async (opts?: CallOpts): Promise<ModelsStatusResponse> => {
  try {
    return await request.get('/transcribers/models/status', cfg(opts))
  } catch (error) {
    if (isNotFoundError(error)) return localModelsStatus()
    throw error
  }
}

export const downloadModel = async (data: {
  model_size: string
  transcriber_type?: string
}) => {
  try {
    return await request.post('/transcribers/models/download', data, cfg())
  } catch (error) {
    if (isNotFoundError(error)) return skippedApiResult()
    throw error
  }
}

export interface WhisperModelsResponse {
  builtin: Record<string, string>
  custom: Record<string, string>
}

export const listWhisperModels = async (opts?: CallOpts): Promise<WhisperModelsResponse> => {
  try {
    return await request.get('/transcribers/whisper-models', cfg(opts))
  } catch (error) {
    if (isNotFoundError(error)) {
      return readLocalValue<WhisperModelsResponse>(
        LOCAL_WHISPER_MODELS_KEY,
        defaultWhisperModels,
      )
    }
    throw error
  }
}

export const addWhisperModel = async (data: { name: string; target: string }) => {
  try {
    return await request.post('/transcribers/whisper-models', data, cfg())
  } catch (error) {
    if (isNotFoundError(error)) {
      const models = readLocalValue<WhisperModelsResponse>(
        LOCAL_WHISPER_MODELS_KEY,
        defaultWhisperModels,
      )
      writeLocalValue(LOCAL_WHISPER_MODELS_KEY, {
        ...models,
        custom: {
          ...models.custom,
          [data.name]: data.target,
        },
      })
      return skippedApiResult()
    }
    throw error
  }
}

export const deleteWhisperModel = async (name: string) => {
  try {
    return await request.delete(`/transcribers/whisper-models/${encodeURIComponent(name)}`, cfg())
  } catch (error) {
    if (isNotFoundError(error)) {
      const models = readLocalValue<WhisperModelsResponse>(
        LOCAL_WHISPER_MODELS_KEY,
        defaultWhisperModels,
      )
      const nextCustom = { ...models.custom }
      delete nextCustom[name]
      writeLocalValue(LOCAL_WHISPER_MODELS_KEY, {
        ...models,
        custom: nextCustom,
      })
      return skippedApiResult()
    }
    throw error
  }
}
