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

interface SearchResultSource {
  chunk?: {
    content?: string
    section_title?: string
    start_time?: number | null
    end_time?: number | null
  }
}

interface QAResponse {
  answer: string
  references?: Reference[]
  sources?: Array<ChatSource | SearchResultSource>
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

function searchResultToSource(source: ChatSource | SearchResultSource): ChatSource {
  if ('source_type' in source && 'text' in source) return source

  const chunk = source.chunk || {}
  const startTime = typeof chunk.start_time === 'number' ? chunk.start_time : undefined
  const endTime = typeof chunk.end_time === 'number' ? chunk.end_time : undefined

  return {
    text: chunk.content || '',
    source_type: typeof startTime === 'number' || typeof endTime === 'number' ? 'transcript' : 'markdown',
    section_title: chunk.section_title,
    start_time: startTime,
    end_time: endTime,
  }
}

export const indexTask = async (taskId: string, videoId?: string): Promise<void> => {
  await request.post('/qa/index', {
    task_id: taskId,
    video_id: videoId,
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
      question: data.question,
      video_id: data.video_id || data.task_id,
      query: data.question,
      stream: false,
      top_k: 5,
      note_id: data.video_id,
      provider_id: data.provider_id,
      model_name: data.model_name,
      history: data.history,
    },
    { timeout: 60000 },
  )

  return {
    answer: res.answer,
    sources: res.sources?.map(searchResultToSource) || (res.references || []).map(referenceToSource),
  }
}

export const askGlobalQuestion = async (data: {
  question: string
  video_ids?: string[]
  top_k?: number
}): Promise<AskResponse> => {
  const res = await request.post<unknown, QAResponse>(
    '/qa/ask-global',
    {
      question: data.question,
      video_ids: data.video_ids,
      top_k: data.top_k ?? 5,
    },
    { timeout: 60000 },
  )

  return {
    answer: res.answer,
    sources: res.sources?.map(searchResultToSource) || (res.references || []).map(referenceToSource),
  }
}

export const getChatStatus = async (
  taskId: string,
  videoId?: string,
): Promise<ChatStatusResponse> => {
  return await request.get('/qa/index/status', {
    params: {
      task_id: taskId,
      video_id: videoId,
    },
    suppressToast: true,
  })
}
