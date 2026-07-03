import request from '@/utils/request'

interface CallOpts {
  silent?: boolean
}

const cfg = (opts?: CallOpts) => (opts?.silent ? { suppressToast: true } : undefined)

export interface VideoItem {
  id: number
  video_id: string
  url: string
  title: string
  uploader?: string | null
  uploader_uid?: string | null
  description?: string | null
  duration_seconds?: number | null
  cover_url?: string | null
  bvid?: string | null
  avid?: number | null
  status: string
  file_size?: number | null
  audio_path?: string | null
  video_path?: string | null
  source_url?: string | null
  player_url?: string | null
  embed_url?: string | null
  upload_date?: string | null
  view_count?: number | null
  like_count?: number | null
  comment_count?: number | null
  tags?: string[]
  chapters?: Array<{
    title?: string
    start_time?: number
    end_time?: number
  }>
  processed_at?: string | null
  created_at: string
  updated_at: string
  tasks?: Array<{
    task_id: string
    type?: string
    status?: string
    progress?: number
  }>
}

export interface VideoListResponse {
  items: VideoItem[]
  total: number
  page: number
  page_size: number
}

export interface ParseVideoResponse {
  video_id: string
  title: string
  uploader?: string | null
  uploader_uid?: string | null
  duration_seconds?: number | null
  cover_url?: string | null
  bvid?: string | null
  avid?: number | null
  description?: string | null
  is_playlist?: boolean
  playlist_title?: string | null
  source_url?: string | null
  player_url?: string | null
  embed_url?: string | null
  upload_date?: string | null
  view_count?: number | null
  like_count?: number | null
  comment_count?: number | null
  tags?: string[]
  chapters?: Array<{
    title?: string
    start_time?: number
    end_time?: number
  }>
}

export const listVideos = async (
  params: { page?: number; page_size?: number; status?: string; search?: string } = {},
  opts?: CallOpts,
): Promise<VideoListResponse> => {
  return await request.get('/videos/', {
    ...(cfg(opts) || {}),
    params,
  })
}

export const getVideo = async (videoId: string, opts?: CallOpts): Promise<VideoItem> => {
  return await request.get(`/videos/${encodeURIComponent(videoId)}`, cfg(opts))
}

export const parseVideo = async (url: string, opts?: CallOpts): Promise<ParseVideoResponse> => {
  return await request.post('/videos/parse', { url }, cfg(opts))
}

export const getNoteRaw = async (videoId: string, opts?: CallOpts): Promise<string> => {
  return await request.get(`/notes/${encodeURIComponent(videoId)}/raw`, {
    ...(cfg(opts) || {}),
    responseType: 'text',
  })
}
