import request from '@/utils/request.ts'

interface CallOpts {
  silent?: boolean
}

const cfg = (opts?: CallOpts) => (opts?.silent ? { suppressToast: true } : undefined)

export interface DownloaderCookie {
  platform: string
  cookie: string
}

export const getDownloaderCookie = async (
  platform?: string,
  opts?: CallOpts,
): Promise<DownloaderCookie | null> => {
  if (!platform) return null

  const data = await request.get<unknown, DownloaderCookie | undefined>(
    `/platforms/${encodeURIComponent(platform)}/cookie`,
    cfg(opts),
  )
  return data || null
}

export const updateDownloaderCookie = async (data: { cookie: string; platform: string }) => {
  return await request.put(`/platforms/${encodeURIComponent(data.platform)}/cookie`, {
    cookie: data.cookie,
  })
}
