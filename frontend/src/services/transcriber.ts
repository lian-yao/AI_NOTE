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
  whisper_device: string
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
  whisper_model_size: 'small',
  whisper_device: 'auto',
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
  whisper_device?: string
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

export interface DownloadProgress {
  model_size: string
  downloading: boolean
  progress: number
  message: string
  failed: boolean
  error: string | null
  elapsed_seconds: number
}

export const getDownloadProgress = async (
  modelSize: string,
  opts?: CallOpts,
): Promise<DownloadProgress> => {
  try {
    return await request.get(
      `/transcribers/models/download/${encodeURIComponent(modelSize)}/progress`,
      cfg(opts),
    )
  } catch (error) {
    if (isNotFoundError(error)) {
      return {
        model_size: modelSize,
        downloading: false,
        progress: 0,
        message: '',
        failed: false,
        error: null,
        elapsed_seconds: 0,
      }
    }
    throw error
  }
}

export const resetDownload = async (modelSize: string) => {
  try {
    return await request.post(
      `/transcribers/models/download/${encodeURIComponent(modelSize)}/reset`,
      undefined,
      cfg(),
    )
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

// ── GPU 加速相关接口 ──

export interface GPUInfo {
  cuda_available: boolean
  cuda_version: string | null
  gpu_name: string | null
  driver_version: string | null
  recommended_package: string | null
  installed_package: string | null
  package_mismatch: boolean
  gpu_deps_installed: boolean
  torch_cuda_available: boolean
  torch_installed: boolean
}

export interface GPUInstallResult {
  task_id: string
  status: string
  package: string
}

export interface GPUInstallProgress {
  task_id: string
  status: 'starting' | 'running' | 'completed' | 'failed' | 'not_found'
  progress: number
  message: string
  error: string | null
  package?: string
}

export const getGPUInfo = async (opts?: CallOpts): Promise<GPUInfo> => {
  try {
    const res = await request.get('/system/gpu/info', cfg(opts))
    return res.data || res
  } catch {
    return {
      cuda_available: false,
      cuda_version: null,
      gpu_name: null,
      driver_version: null,
      recommended_package: null,
      gpu_deps_installed: false,
      torch_cuda_available: false,
      torch_installed: false,
    }
  }
}

export const installGPUDrivers = async (): Promise<GPUInstallResult> => {
  const res = await request.post('/system/gpu/install', undefined, cfg())
  return res.data || res
}

export const getGPUInstallProgress = async (
  taskId: string,
  opts?: CallOpts,
): Promise<GPUInstallProgress> => {
  const res = await request.get(
    `/system/gpu/install/${encodeURIComponent(taskId)}/progress`,
    cfg(opts),
  )
  return res.data || res
}

export const uninstallGPUDrivers = async () => {
  return await request.delete('/system/gpu/uninstall', cfg())
}
