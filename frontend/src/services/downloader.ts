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
  id?: string,
  opts?: CallOpts,
): Promise<DownloaderCookie | null> => {
  if (!id) return null

  const data = await request.get<unknown, DownloaderCookie | undefined>(
    '/get_downloader_cookie/' + id,
    cfg(opts),
  )
  return data || null
}

export const updateDownloaderCookie = async (data: { cookie: string; platform: string }) => {
  return await request.post('/update_downloader_cookie', data)
}
