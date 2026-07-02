import request, { isNotFoundError } from '@/utils/request'
import { readLocalValue, writeLocalValue } from '@/services/fallback'

interface CallOpts {
  silent?: boolean
}

const cfg = (opts?: CallOpts) => ({
  ...(opts?.silent ? { suppressToast: true } : {}),
  suppressNotFoundToast: true,
})
const LOCAL_PROXY_CONFIG_KEY = 'ai-note:proxy-config:fallback'

const defaultProxyConfig: ProxyConfig = {
  enabled: false,
  url: '',
  effective: '',
}

export interface ProxyConfig {
  enabled: boolean
  url: string
  effective: string
}

export const getProxyConfig = async (opts?: CallOpts): Promise<ProxyConfig> => {
  try {
    return await request.get('/network/proxy', cfg(opts))
  } catch (error) {
    if (isNotFoundError(error)) {
      return readLocalValue<ProxyConfig>(LOCAL_PROXY_CONFIG_KEY, defaultProxyConfig)
    }
    throw error
  }
}

export const updateProxyConfig = async (data: {
  enabled: boolean
  url?: string
}): Promise<ProxyConfig> => {
  try {
    return await request.put('/network/proxy', data, cfg())
  } catch (error) {
    if (isNotFoundError(error)) {
      const config = {
        enabled: data.enabled,
        url: data.url || '',
        effective: data.enabled ? data.url || '' : '',
      }
      writeLocalValue(LOCAL_PROXY_CONFIG_KEY, config)
      return config
    }
    throw error
  }
}
