import request, { isNotFoundError } from '@/utils/request'

interface CallOpts {
  silent?: boolean
}

const cfg = (opts?: CallOpts) => (opts?.silent ? { suppressToast: true } : undefined)
const pendingCfg = (opts?: CallOpts) => ({
  ...(opts?.silent ? { suppressToast: true } : {}),
  suppressNotFoundToast: true,
})

export interface SysHealth {
  status: 'healthy' | 'degraded' | string
  database: string
  vector_store: string
  llm_api: string
  embedding_api: string
  disk_space: string
  uptime_seconds: number
}

export const getSysHealth = async (opts?: CallOpts): Promise<SysHealth> => {
  return await request.get('/system/health', cfg(opts))
}

export const systemCheck = getSysHealth

export interface SystemConfig {
  llm_provider: string
  llm_model?: string
  transcriber_mode: string
  whisper_model_size: string
  whisper_device: string
  embedding_model: string
  retrieval_top_k: number
  data_dir: string
  video_retention: string
}

export interface SystemStats {
  total_videos: number
  completed_videos: number
  total_notes: number
  total_chunks: number
  total_duration_hours: number
  storage_usage_bytes: number
  disk_free_bytes: number
}

export const getSystemConfig = async (opts?: CallOpts): Promise<SystemConfig> => {
  return await request.get('/system/config', cfg(opts))
}

export const updateSystemConfig = async (
  data: Partial<
    Pick<SystemConfig, 'llm_provider' | 'transcriber_mode' | 'retrieval_top_k' | 'whisper_model_size' | 'whisper_device'>
  >,
): Promise<{ updated_fields: string[] }> => {
  return await request.put('/system/config', data)
}

export const saveSystemConfig = async (): Promise<{ message: string }> => {
  return await request.post('/system/config/save')
}

export const getSystemStats = async (opts?: CallOpts): Promise<SystemStats> => {
  return await request.get('/system/stats', cfg(opts))
}

export interface DeployStatus {
  backend: {
    status: string
    port: number
  }
  cuda: {
    available: boolean
    torch_installed?: boolean
    version: string | null
    gpu_name: string | null
  }
  whisper: {
    model_size: string
    transcriber_type: string
    downloaded: boolean
  }
  ffmpeg: {
    available: boolean
  }
}

const fallbackDeployStatus: DeployStatus = {
  backend: {
    status: 'unknown',
    port: 0,
  },
  cuda: {
    available: false,
    version: null,
    gpu_name: null,
  },
  whisper: {
    model_size: '-',
    transcriber_type: 'unknown',
    downloaded: false,
  },
  ffmpeg: {
    available: false,
  },
}

export const getDeployStatus = async (opts?: CallOpts): Promise<DeployStatus> => {
  try {
    return await request.get('/system/deploy-status', pendingCfg(opts))
  } catch (error) {
    if (isNotFoundError(error)) return fallbackDeployStatus
    throw error
  }
}
