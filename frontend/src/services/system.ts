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
