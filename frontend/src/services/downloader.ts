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
