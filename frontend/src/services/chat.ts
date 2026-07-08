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

type StreamSource = Partial<ChatSource> & {
  start_time?: number | null
  end_time?: number | null
}

interface StreamEvent {
  token?: string
  sources?: StreamSource[]
  done?: boolean
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

export const askQuestionStream = async (
  data: {
    task_id?: string
    video_id?: string
    question: string
    history: ChatMessage[]
    provider_id: string
    model_name: string
  },
  onToken: (token: string) => void,
  onSources: (sources: ChatSource[]) => void,
  onDone: () => void,
): Promise<void> => {
  const apiBase = (() => {
    const raw = import.meta.env.VITE_API_BASE_URL || '/api/v1'
    return raw.replace(/\/+$/, '')
  })()
  const url = `${apiBase}/qa/ask/stream`

  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        question: data.question,
        video_id: data.video_id || data.task_id,
        note_id: data.video_id,
        top_k: 5,
      }),
    })

    if (!response.ok || !response.body) {
      throw new Error('stream not available')
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        try {
          const parsed = JSON.parse(line.slice(6)) as StreamEvent
          if (parsed.token) {
            onToken(parsed.token)
          }
          if (Array.isArray(parsed.sources)) {
            onSources(parsed.sources.map(s => ({
              text: s.text || '',
              source_type: s.start_time != null ? 'transcript' as const : 'markdown' as const,
              section_title: s.section_title,
              start_time: s.start_time,
              end_time: s.end_time,
            })))
          }
          if (parsed.done) {
            onDone()
          }
        } catch {
          // skip malformed JSON
        }
      }
    }
  } catch {
    // fallback to non-streaming
    const res = await askQuestion(data)
    onToken(res.answer)
    onSources(res.sources || [])
    onDone()
  }
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
