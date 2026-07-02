import request from '@/utils/request'

interface CallOpts {
  silent?: boolean
}

const cfg = (opts?: CallOpts) => (opts?.silent ? { suppressToast: true } : undefined)

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

export const getTranscriberConfig = async (opts?: CallOpts): Promise<TranscriberConfig> => {
  return await request.get('/transcribers/config', cfg(opts))
}

export const updateTranscriberConfig = async (data: {
  transcriber_type: string
  whisper_model_size?: string
}) => {
  return await request.put('/transcribers/config', data)
}

export const getModelsStatus = async (opts?: CallOpts): Promise<ModelsStatusResponse> => {
  return await request.get('/transcribers/models/status', cfg(opts))
}

export const downloadModel = async (data: {
  model_size: string
  transcriber_type?: string
}) => {
  return await request.post('/transcribers/models/download', data)
}

export interface WhisperModelsResponse {
  builtin: Record<string, string>
  custom: Record<string, string>
}

export const listWhisperModels = async (opts?: CallOpts): Promise<WhisperModelsResponse> => {
  return await request.get('/transcribers/whisper-models', cfg(opts))
}

export const addWhisperModel = async (data: { name: string; target: string }) => {
  return await request.post('/transcribers/whisper-models', data)
}

export const deleteWhisperModel = async (name: string) => {
  return await request.delete(`/transcribers/whisper-models/${encodeURIComponent(name)}`)
}
