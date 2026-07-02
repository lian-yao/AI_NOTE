import request from '@/utils/request'

interface CallOpts {
  silent?: boolean
}

const cfg = (opts?: CallOpts) => (opts?.silent ? { suppressToast: true } : undefined)

export interface ProxyConfig {
  enabled: boolean
  url: string
  effective: string
}

export const getProxyConfig = async (opts?: CallOpts): Promise<ProxyConfig> => {
  return await request.get('/network/proxy', cfg(opts))
}

export const updateProxyConfig = async (data: {
  enabled: boolean
  url?: string
}): Promise<ProxyConfig> => {
  return await request.put('/network/proxy', data)
}
