import request from '@/utils/request'

interface CallOpts {
  silent?: boolean
}

const cfg = (opts?: CallOpts) => (opts?.silent ? { suppressToast: true } : undefined)

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

export const getDeployStatus = async (opts?: CallOpts): Promise<DeployStatus> => {
  return await request.get('/system/deploy-status', cfg(opts))
}
