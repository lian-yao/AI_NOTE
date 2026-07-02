import request from '@/utils/request'
import toast from 'react-hot-toast'
import type { AudioMeta, TaskStatus, Transcript } from '@/store/taskStore'

export interface GenerateNotePayload {
  video_url: string
  platform: string
  quality: string
  link?: boolean
  screenshot?: boolean
  model_name: string
  provider_id: string
  task_id?: string
  format?: string[]
  style?: string
  extras?: string
  video_understanding?: boolean
  video_interval?: number
  grid_size?: number[]
}

export interface GenerateNoteResponse {
  video_id?: string
  task_id: string
  status?: string
}

export interface TaskStatusResponse {
  status: TaskStatus
  task_id: string
  video_id?: string
  message?: string
  result?: {
    markdown: string
    transcript: Transcript
    audio_meta: AudioMeta
  } | null
}

const validQualities = new Set(['360p', '480p', '720p', '1080p'])

function normalizeQuality(quality?: string): string {
  return quality && validQualities.has(quality) ? quality : '1080p'
}

function normalizeFormat(data: GenerateNotePayload): string[] {
  if (data.format?.length) return data.format

  const format = ['summary']
  if (data.link) format.unshift('link')
  if (data.screenshot) format.unshift('screenshot')
  return [...new Set(format)]
}

function normalizeTaskStatus(status?: string): TaskStatus {
  const value = (status || '').toLowerCase()

  if (value === 'completed' || value === 'success') return 'SUCCESS'
  if (value === 'failed') return 'FAILED'
  if (value === 'pending') return 'PENDING'
  if (value === 'running' || value === 'retrying') return 'RUNNING'
  if (value === 'downloading') return 'DOWNLOADING'
  if (value === 'transcribing') return 'TRANSCRIBING'
  if (value === 'generating') return 'SUMMARIZING'
  if (value === 'storing') return 'SAVING'

  return (status?.toUpperCase() as TaskStatus | undefined) || 'RUNNING'
}

export const generateNote = async (data: GenerateNotePayload): Promise<GenerateNoteResponse> => {
  const body = {
    url: data.video_url,
    quality: normalizeQuality(data.quality),
    provider_id: data.provider_id,
    model_name: data.model_name,
    format: normalizeFormat(data),
    style: data.style || 'minimal',
    extras: data.extras,
    video_understanding: data.video_understanding ?? false,
    video_interval: data.video_interval ?? 6,
    grid_size: data.grid_size ?? [2, 2],
    ...(data.platform === 'local' ? { platform: 'local' } : {}),
    ...(data.task_id ? { task_id: data.task_id } : {}),
  }

  const response = await request.post<unknown, GenerateNoteResponse>('/videos/process', body)
  toast.success('笔记生成任务已提交')
  return response
}

export const delete_task = async ({ video_id }: { video_id: string; platform: string }) => {
  if (!video_id) return null

  const res = await request.delete(`/videos/${encodeURIComponent(video_id)}`)
  toast.success('任务已成功删除')
  return res
}

export const get_task_status = async (task_id: string): Promise<TaskStatusResponse> => {
  const response = await request.get<unknown, Omit<TaskStatusResponse, 'status'> & { status: string }>(
    `/tasks/${encodeURIComponent(task_id)}`,
  )

  return {
    ...response,
    status: normalizeTaskStatus(response.status),
  }
}
