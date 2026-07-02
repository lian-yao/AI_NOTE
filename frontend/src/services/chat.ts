import request from '@/utils/request'

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

export interface ChatSource {
  text: string
  source_type: 'markdown' | 'transcript'
  section_title?: string
  start_time?: number
  end_time?: number
}

export interface AskResponse {
  answer: string
  sources: ChatSource[]
}

export type IndexStatus = 'idle' | 'indexing' | 'indexed' | 'failed'

export interface ChatStatusResponse {
  indexed: boolean
  status: IndexStatus
}

interface Reference {
  content: string
  section_title?: string
  start_time?: number
  end_time?: number
}

interface QAResponse {
  answer: string
  references?: Reference[]
  sources?: ChatSource[]
}

function referenceToSource(reference: Reference): ChatSource {
  return {
    text: reference.content,
    source_type:
      typeof reference.start_time === 'number' || typeof reference.end_time === 'number'
        ? 'transcript'
        : 'markdown',
    section_title: reference.section_title,
    start_time: reference.start_time,
    end_time: reference.end_time,
  }
}

export const indexTask = async (taskId: string, videoId?: string): Promise<void> => {
  await request.post('/qa/index', {
    task_id: taskId,
    ...(videoId ? { video_id: videoId } : {}),
  })
}

export const askQuestion = async (data: {
  task_id?: string
  video_id?: string
  question: string
  history: ChatMessage[]
  provider_id: string
  model_name: string
}): Promise<AskResponse> => {
  const res = await request.post<unknown, QAResponse>(
    '/qa/ask',
    {
      video_id: data.video_id || data.task_id,
      query: data.question,
      stream: false,
      top_k: 5,
      provider_id: data.provider_id,
      model_name: data.model_name,
      history: data.history,
    },
    { timeout: 60000 },
  )

  return {
    answer: res.answer,
    sources: res.sources || (res.references || []).map(referenceToSource),
  }
}

export const getChatStatus = async (
  taskId: string,
  videoId?: string,
): Promise<ChatStatusResponse> => {
  const params = new URLSearchParams()
  if (taskId) params.set('task_id', taskId)
  if (videoId) params.set('video_id', videoId)

  return await request.get(`/qa/index/status?${params.toString()}`)
}
