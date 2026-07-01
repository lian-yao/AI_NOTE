import request from '@/utils/request'

interface CallOpts {
  silent?: boolean
}

const cfg = (opts?: CallOpts) => (opts?.silent ? { suppressToast: true } : undefined)

export interface ProxyConfig {
  enabled: boolean
  url: string
  /** 后端实际生效的代理（可能来自配置，也可能来自 HTTP_PROXY 环境变量兜底） */
  effective: string
}

export const getProxyConfig = async (opts?: CallOpts): Promise<ProxyConfig> => {
  return await request.get('/proxy_config', cfg(opts))
}

export const updateProxyConfig = async (data: {
  enabled: boolean
  url?: string
}): Promise<ProxyConfig> => {
  return await request.post('/proxy_config', data)
}
