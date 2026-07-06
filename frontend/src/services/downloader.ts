import request, { isNotFoundError } from '@/utils/request.ts'
import { readLocalValue, writeLocalValue } from '@/services/fallback'

interface CallOpts {
  silent?: boolean
}

const cfg = (opts?: CallOpts) => ({
  ...(opts?.silent ? { suppressToast: true } : {}),
  suppressNotFoundToast: true,
})
const LOCAL_DOWNLOADER_COOKIES_KEY = 'ai-note:downloader-cookies:fallback'

export interface DownloaderCookie {
  platform: string
  cookie: string
}

export interface DownloaderCookieValidation {
  platform: string
  valid: boolean
  is_login: boolean
  username?: string | null
  mid?: number | string | null
  level?: number | string | null
  vip_status?: number | string | null
  vip_type?: number | string | null
  message?: string | null
}

export interface DownloaderCookieImportResult extends DownloaderCookieValidation {
  cookie: string
  browser?: string
  saved?: boolean
}

export interface PlatformLoginOpenResult {
  platform: string
  browser?: string
  url?: string
  opened: boolean
  message?: string | null
}

export interface BilibiliQrCodeSession {
  platform: string
  qrcode_key: string
  url: string
  expires_in?: number
  poll_interval?: number
  message?: string | null
}

export type BilibiliQrCodeLoginStatus = 'pending' | 'scanned' | 'confirmed' | 'expired' | 'failed'

export interface BilibiliQrCodePollResult extends DownloaderCookieValidation {
  qrcode_key: string
  status: BilibiliQrCodeLoginStatus
  login_code?: number | string | null
  cookie?: string
  saved?: boolean
  refresh_token?: string
  url?: string
}

export const getDownloaderCookie = async (
  platform?: string,
  opts?: CallOpts,
): Promise<DownloaderCookie | null> => {
  if (!platform) return null

  try {
    const data = await request.get<unknown, DownloaderCookie | undefined>(
      `/platforms/${encodeURIComponent(platform)}/cookie`,
      cfg(opts),
    )
    return data || null
  } catch (error) {
    if (isNotFoundError(error)) {
      const cookies = readLocalValue<Record<string, string>>(LOCAL_DOWNLOADER_COOKIES_KEY, {})
      return cookies[platform] ? { platform, cookie: cookies[platform] } : null
    }
    throw error
  }
}

export const updateDownloaderCookie = async (data: { cookie: string; platform: string }) => {
  try {
    return await request.put(
      `/platforms/${encodeURIComponent(data.platform)}/cookie`,
      { cookie: data.cookie },
      cfg(),
    )
  } catch (error) {
    if (isNotFoundError(error)) {
      const cookies = readLocalValue<Record<string, string>>(LOCAL_DOWNLOADER_COOKIES_KEY, {})
      writeLocalValue(LOCAL_DOWNLOADER_COOKIES_KEY, {
        ...cookies,
        [data.platform]: data.cookie,
      })
      return data
    }
    throw error
  }
}

export const validateDownloaderCookie = async (
  data: { cookie?: string; platform: string },
  opts?: CallOpts,
): Promise<DownloaderCookieValidation> => {
  return await request.post(
    `/platforms/${encodeURIComponent(data.platform)}/cookie/validate`,
    { cookie: data.cookie },
    cfg(opts),
  )
}

export const importDownloaderCookieFromBrowser = async (
  data: { browser?: string; platform: string },
  opts?: CallOpts,
): Promise<DownloaderCookieImportResult> => {
  return await request.post(
    `/platforms/${encodeURIComponent(data.platform)}/cookie/import-browser`,
    { browser: data.browser, save: true },
    cfg(opts),
  )
}

export const startBilibiliQrCodeLogin = async (
  platform = 'bilibili',
  opts?: CallOpts,
): Promise<BilibiliQrCodeSession> => {
  return await request.post(
    `/platforms/${encodeURIComponent(platform)}/qrcode/start`,
    {},
    cfg(opts),
  )
}

export const pollBilibiliQrCodeLogin = async (
  data: { platform?: string; qrcode_key: string; save?: boolean },
  opts?: CallOpts,
): Promise<BilibiliQrCodePollResult> => {
  const platform = data.platform || 'bilibili'
  return await request.post(
    `/platforms/${encodeURIComponent(platform)}/qrcode/poll`,
    { qrcode_key: data.qrcode_key, save: data.save !== false },
    cfg(opts),
  )
}

export const openPlatformLoginInBrowser = async (
  data: { browser?: string; platform: string },
  opts?: CallOpts,
): Promise<PlatformLoginOpenResult> => {
  return await request.post(
    `/platforms/${encodeURIComponent(data.platform)}/login-browser`,
    { browser: data.browser },
    cfg(opts),
  )
}
