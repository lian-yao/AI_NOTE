import request from '@/utils/request'
import toast from 'react-hot-toast'
import type { AudioMeta, TaskStatus, Transcript } from '@/store/taskStore'

interface CallOpts {
  silent?: boolean
}

const cfg = (opts?: CallOpts) => (opts?.silent ? { suppressToast: true } : undefined)

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
  result?: TaskStatusResponse['result']
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

export interface NoteMeta {
  id: number
  video_id: number
  file_path: string
  summary?: string | null
  keywords?: string | null
  total_chunks: number
  section_count: number
  char_count: number
  model_used?: string | null
  created_at: string
  updated_at: string
}

export interface CreateNotePayload {
  video_id: number
  file_path: string
  summary?: string | null
  keywords?: string | null
  total_chunks?: number
  section_count?: number
  char_count?: number
  model_used?: string | null
}

const validQualities = new Set(['360p', '480p', '720p', '1080p'])

interface DirectNoteResponse {
  id?: number | string
  video_id?: number | string
  file_path?: string
  summary?: string | null
}

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

function createEmptyTranscript(): Transcript {
  return {
    full_text: '',
    language: 'zh-CN',
    raw: null,
    segments: [],
  }
}

function createAudioMeta(data: {
  videoId?: number | string
  filePath?: string
  platform?: string
  title?: string
}): AudioMeta {
  return {
    cover_url: '',
    duration: 0,
    file_path: data.filePath || '',
    platform: data.platform || '',
    raw_info: null,
    title: data.title || '笔记已生成',
    video_id: data.videoId == null ? '' : String(data.videoId),
  }
}

function createCompletedResult(data: {
  videoId?: number | string
  filePath?: string
  platform?: string
  title?: string
  summary?: string | null
}): NonNullable<TaskStatusResponse['result']> {
  const summary = data.summary?.trim()
  const markdown = summary
    ? `# 笔记已生成\n\n${summary}`
    : '# 笔记已生成\n\n当前后端已完成处理，但任务状态接口暂未返回完整 Markdown 内容。'

  return {
    markdown,
    transcript: createEmptyTranscript(),
    audio_meta: createAudioMeta(data),
  }
}

function normalizeGenerateResponse(
  response: GenerateNoteResponse | DirectNoteResponse,
  data: GenerateNotePayload,
): GenerateNoteResponse {
  if ('task_id' in response && response.task_id) return response

  const note = response as DirectNoteResponse
  const videoId = note.video_id == null ? undefined : String(note.video_id)
  return {
    task_id: data.task_id || `note_${note.id || Date.now()}`,
    video_id: videoId,
    status: 'completed',
    result: createCompletedResult({
      videoId,
      filePath: note.file_path,
      platform: data.platform,
      title: data.video_url,
      summary: note.summary,
    }),
  }
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

  const response = await request.post<unknown, GenerateNoteResponse | DirectNoteResponse>('/videos/process', body)
  const normalized = normalizeGenerateResponse(response, data)
  toast.success(normalized.result ? '笔记已生成' : '笔记生成任务已提交')
  return normalized
}

export const listNotes = async (opts?: CallOpts): Promise<NoteMeta[]> => {
  return await request.get('/notes/', cfg(opts))
}

export const getNote = async (noteId: number | string, opts?: CallOpts): Promise<NoteMeta> => {
  return await request.get(`/notes/${encodeURIComponent(String(noteId))}`, cfg(opts))
}

export const createNote = async (
  data: CreateNotePayload,
  opts?: CallOpts,
): Promise<NoteMeta> => {
  return await request.post('/notes/', data, cfg(opts))
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

  const status = normalizeTaskStatus(response.status)
  const result =
    status === 'SUCCESS' && !response.result
      ? createCompletedResult({
        videoId: response.video_id,
        platform: '',
      })
      : response.result

  return {
    ...response,
    task_id: response.task_id || task_id,
    video_id: response.video_id == null ? undefined : String(response.video_id),
    status,
    result,
  }
}


export const cancelBackendTask = async (taskId: string): Promise<void> => {
  return await request.post(/tasks//cancel)
}
