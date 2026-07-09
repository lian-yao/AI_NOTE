import { useState, useEffect, useCallback, useMemo, type ReactNode } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Button } from '@/components/ui/button'
import {
  Loader2,
  Trash2,
  ChevronDown,
  ChevronUp,
  BookOpen,
  UserRound,
  Bot,
  Maximize2,
  Minimize2,
  SendHorizontal,
} from 'lucide-react'
import { toast } from 'react-hot-toast'
import { cn } from '@/lib/utils'
import { useChatStore } from '@/store/chatStore'
import { useTaskStore } from '@/store/taskStore'
import {
  askQuestionStream,
  getChatStatus,
  indexTask,
  type ChatSource,
  type IndexStatus,
} from '@/services/chat'

type ChatMode = 'half' | 'full'

interface ChatPanelProps {
  taskId: string
  mode: ChatMode
  onModeChange: (mode: ChatMode) => void
  title?: string
  headerActions?: ReactNode
  showModeToggle?: boolean
}

const assistantMarkdownClassName = cn(
  'max-w-none break-words leading-6 text-neutral-200',
  '[&>*:first-child]:mt-0 [&>*:last-child]:mb-0',
  '[&_p]:my-1 [&_li]:my-0.5 [&_ol]:pl-5 [&_ul]:pl-5',
  '[&_hr]:my-3 [&_hr]:border-neutral-800',
  '[&_blockquote]:my-2 [&_blockquote]:border [&_blockquote]:border-blue-400/15 [&_blockquote]:border-l-blue-400/55',
  '[&_blockquote]:bg-blue-500/10 [&_blockquote]:px-3 [&_blockquote]:py-2 [&_blockquote]:text-neutral-200',
  '[&_blockquote]:shadow-[inset_3px_0_0_rgba(96,165,250,0.45)]',
  '[&_blockquote_p]:my-0.5 [&_blockquote_p]:text-neutral-200',
)

function stripInlineReferenceSection(content: string) {
  const markerIndex = content.search(
    /\n{0,2}---\s*\n\s*(?:\*\*)?\s*引用来源\s*(?:\*\*)?\s*[：:]/,
  )
  return markerIndex >= 0 ? content.slice(0, markerIndex).trimEnd() : content
}

function formatSourceTime(seconds?: number) {
  if (typeof seconds !== 'number' || Number.isNaN(seconds)) return ''

  const totalSeconds = Math.max(0, Math.floor(seconds))
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const secs = totalSeconds % 60

  if (hours > 0) {
    return `${hours}:${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`
  }
  return `${minutes}:${String(secs).padStart(2, '0')}`
}

function getSourceTitle(source: ChatSource, index: number) {
  const sectionTitle = source.section_title?.trim()
  if (sectionTitle) return sectionTitle
  return source.source_type === 'transcript' ? `字幕片段 ${index + 1}` : `笔记片段 ${index + 1}`
}

function getSourceTimeRange(source: ChatSource) {
  const start = formatSourceTime(source.start_time)
  const end = formatSourceTime(source.end_time)

  if (start && end && start !== end) return `${start} - ${end}`
  return start || end
}

function SourceText({ text }: { text: string }) {
  const [expanded, setExpanded] = useState(false)
  const content = text.trim() || '没有返回引用文本'
  const shouldClamp = content.length > 160 || content.includes('\n')

  return (
    <div>
      <p
        className={cn(
          'whitespace-pre-wrap break-words text-xs leading-5 text-neutral-300',
          shouldClamp && !expanded && 'max-h-[3.75rem] overflow-hidden',
        )}
      >
        {content}
      </p>
      {shouldClamp && (
        <button
          type="button"
          onClick={() => setExpanded(!expanded)}
          className="mt-1 text-xs text-neutral-500 transition-colors hover:text-neutral-300"
        >
          {expanded ? '收起原文' : '展开原文'}
        </button>
      )}
    </div>
  )
}

function SourceReferences({ sources }: { sources: ChatSource[] }) {
  const [expanded, setExpanded] = useState(false)

  if (!sources || sources.length === 0) return null

  return (
    <div className="mt-3 border-t border-neutral-800/80 pt-2">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1.5 text-xs text-neutral-500 transition-colors hover:text-neutral-300"
      >
        <BookOpen className="h-3 w-3" />
        <span>引用来源 ({sources.length})</span>
        {expanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
      </button>
      {expanded && (
        <div className="mt-2 space-y-2">
          {sources.map((s, i) => {
            const timeRange = getSourceTimeRange(s)

            return (
              <div key={i} className="rounded-md border border-neutral-800/80 px-2.5 py-2">
                <div className="mb-1.5 flex min-w-0 items-center justify-between gap-2">
                  <span className="min-w-0 truncate text-xs font-medium text-neutral-300">
                    {i + 1}. {getSourceTitle(s, i)}
                  </span>
                  {timeRange && (
                    <span className="shrink-0 text-[11px] text-neutral-500">{timeRange}</span>
                  )}
                </div>
                <SourceText text={s.text || ''} />
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

export default function ChatPanel({
  taskId,
  mode,
  onModeChange,
  title = 'AI 问答',
  headerActions,
  showModeToggle = true,
}: ChatPanelProps) {
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [indexStatus, setIndexStatus] = useState<IndexStatus | null>(null)
  const [streamingAssistant, setStreamingAssistant] = useState<{
    content: string
    sources: ChatSource[]
  } | null>(null)

  const rawMessages = useChatStore(state => state.chatHistory?.[taskId])
  const messages = useMemo(
    () =>
      Array.isArray(rawMessages)
        ? rawMessages
            .filter(msg => msg && (msg.role === 'user' || msg.role === 'assistant'))
            .map(msg => ({
              ...msg,
              content: stripInlineReferenceSection(
                typeof msg.content === 'string' ? msg.content : String(msg.content ?? ''),
              ),
              sources: Array.isArray(msg.sources) ? msg.sources : undefined,
            }))
        : [],
    [rawMessages]
  )
  const renderedMessages = useMemo(() => {
    if (!streamingAssistant || (!streamingAssistant.content && streamingAssistant.sources.length === 0)) {
      return messages
    }

    return [
      ...messages,
      {
        role: 'assistant' as const,
        content: streamingAssistant.content,
        sources: streamingAssistant.sources,
      },
    ]
  }, [messages, streamingAssistant])
  const addMessage = useChatStore(state => state.addMessage)
  const clearChat = useChatStore(state => state.clearChat)

  const tasks = useTaskStore(state => state.tasks)
  const currentTask = useMemo(() => tasks.find(t => t.id === taskId) ?? null, [tasks, taskId])
  const videoId = currentTask?.audioMeta?.video_id

  // 检查索引状态，未索引时自动触发，indexing 时轮询
  useEffect(() => {
    if (!taskId) return
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | null = null

    const poll = async () => {
      try {
        const res = await getChatStatus(taskId, videoId)
        if (cancelled) return
        setIndexStatus(res.status)

        if (res.status === 'idle') {
          // 未索引，触发后台索引
          await indexTask(taskId, videoId)
          if (!cancelled) setIndexStatus('indexing')
        }

        // indexing 状态持续轮询
        if (res.status === 'indexing' || res.status === 'idle') {
          timer = setTimeout(poll, 2000)
        }
      } catch {
        if (!cancelled) setIndexStatus('failed')
      }
    }

    poll()
    return () => {
      cancelled = true
      if (timer) clearTimeout(timer)
    }
  }, [taskId, videoId])

  const handleSend = useCallback(
    async (value: string) => {
      const question = value.trim()
      if (!question || loading) return

      const providerId = currentTask?.formData?.provider_id
      const modelName = currentTask?.formData?.model_name
      if (!providerId || !modelName || !videoId) {
        toast.error('无法获取问答所需的视频或模型配置，请确认任务已完成')
        return
      }

      addMessage(taskId, { role: 'user', content: question })
      setInput('')
      setLoading(true)
      setStreamingAssistant({ content: '', sources: [] })
      const history = messages.slice(-20).map(m => ({ role: m.role, content: m.content }))

      try {
        let answer = ''
        let sources: ChatSource[] = []

        await askQuestionStream(
          {
            task_id: taskId,
            video_id: videoId,
            question,
            history,
            provider_id: providerId,
            model_name: modelName,
          },
          token => {
            answer += token
            const cleanedAnswer = stripInlineReferenceSection(answer)
            setStreamingAssistant(prev => ({
              content: cleanedAnswer,
              sources: prev?.sources ?? sources,
            }))
          },
          nextSources => {
            sources = nextSources
            setStreamingAssistant(prev => ({
              content: prev?.content ?? stripInlineReferenceSection(answer),
              sources,
            }))
          },
          () => undefined,
        )

        const cleanedAnswer = stripInlineReferenceSection(answer)
        addMessage(taskId, {
          role: 'assistant',
          content: cleanedAnswer.trim() ? cleanedAnswer : '未生成回答',
          sources,
        })
      } catch {
        toast.error('问答请求失败')
      } finally {
        setLoading(false)
        setStreamingAssistant(null)
      }
    },
    [loading, taskId, currentTask, videoId, messages, addMessage]
  )

  if (indexStatus === null || indexStatus === 'indexing' || indexStatus === 'idle') {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 bg-[#151515] text-neutral-400">
        <Loader2 className="text-primary h-6 w-6 animate-spin" />
        <div className="text-center">
          <p className="text-sm font-medium text-neutral-200">正在索引笔记内容...</p>
          <p className="mt-1 text-xs text-neutral-500">
            使用设置中的 Embedding 配置；未配置 API Key 时会自动降级为关键词检索。
          </p>
        </div>
      </div>
    )
  }

  if (indexStatus === 'failed') {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 bg-[#151515] text-neutral-400">
        <span className="text-sm">索引失败，请重试</span>
        <button
          type="button"
          onClick={async () => {
            setIndexStatus('indexing')
            try {
              await indexTask(taskId, videoId)
            } catch {
              toast.error('索引请求失败')
              setIndexStatus('failed')
            }
          }}
          className="rounded-md border border-neutral-700 bg-[#1D1D1F] px-3 py-1.5 text-xs font-medium text-neutral-200 transition-colors hover:border-neutral-600 hover:bg-[#242428]"
        >
          重新索引
        </button>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col overflow-hidden bg-[#151515]">
      {/* 头部 */}
      <div className="flex h-11 shrink-0 items-center justify-between border-b border-neutral-800/90 bg-[#171719] px-3">
        <span className="flex items-center gap-2 text-sm font-medium text-neutral-200">
          <Bot className="text-primary h-4 w-4" />
          {title}
        </span>
        <div className="flex items-center gap-1.5">
          {headerActions}
          {showModeToggle && (
            <Button
              variant="ghost"
              size="sm"
              className="h-7 px-2 text-neutral-500 hover:bg-neutral-800 hover:text-neutral-200"
              onClick={() => onModeChange(mode === 'half' ? 'full' : 'half')}
              title={mode === 'half' ? '全屏' : '半屏'}
            >
              {mode === 'half' ? (
                <Maximize2 className="h-3.5 w-3.5" />
              ) : (
                <Minimize2 className="h-3.5 w-3.5" />
              )}
            </Button>
          )}
          {messages.length > 0 && (
            <Button
              variant="ghost"
              size="sm"
              className="h-7 px-2 text-neutral-500 hover:bg-red-500/10 hover:text-red-400"
              onClick={() => clearChat(taskId)}
              title="清空对话"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          )}
        </div>
      </div>

      {/* 消息列表 */}
      <div className="custom-scrollbar flex-1 overflow-y-auto bg-[#151515] p-4">
        {renderedMessages.length === 0 && !loading ? (
          <div className="flex h-full items-center justify-center text-center text-sm text-neutral-400">
            <div>
              <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-full border border-neutral-800 bg-[#1D1D1F]">
                <Bot className="text-primary h-5 w-5" />
              </div>
              <p className="font-medium text-neutral-200">针对笔记内容提问</p>
              <p className="mt-1 text-xs text-neutral-500">例如：这个视频的核心观点是什么？</p>
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            {renderedMessages.map((msg, index) => {
              const isUser = msg.role === 'user'
              return (
                <div
                  key={`${msg.role}-${index}`}
                  className={`flex gap-2 ${isUser ? 'justify-end' : 'justify-start'}`}
                >
                  {!isUser && (
                    <div className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-neutral-700 bg-[#222225] text-neutral-200">
                      <Bot className="h-4 w-4" />
                    </div>
                  )}
                  <div
                    className={cn(
                      'min-w-0 text-sm',
                      isUser
                        ? 'bg-primary max-w-[78%] rounded-lg px-3 py-2 text-white'
                        : 'flex-1 py-1 text-neutral-200',
                    )}
                  >
                    {isUser ? (
                      <p className="break-words whitespace-pre-wrap">{msg.content}</p>
                    ) : (
                      <div className={assistantMarkdownClassName}>
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                      </div>
                    )}
                    {msg.role === 'assistant' && Array.isArray(msg.sources) && (
                      <SourceReferences sources={msg.sources} />
                    )}
                  </div>
                  {isUser && (
                    <div className="bg-primary mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-white">
                      <UserRound className="h-4 w-4" />
                    </div>
                  )}
                </div>
              )
            })}
            {loading && !streamingAssistant?.content && (
              <div className="flex items-center gap-2 text-sm text-neutral-400">
                <Loader2 className="text-primary h-4 w-4 animate-spin" />
                思考中...
              </div>
            )}
          </div>
        )}
      </div>

      {/* 输入区域 */}
      <form
        className="flex shrink-0 gap-2 border-t border-neutral-800/90 bg-[#171719] p-3"
        onSubmit={event => {
          event.preventDefault()
          void handleSend(input)
        }}
      >
        <textarea
          value={input}
          onChange={event => setInput(event.target.value)}
          onKeyDown={event => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault()
              void handleSend(input)
            }
          }}
          rows={1}
          placeholder="输入你的问题..."
          className="focus:border-primary/70 focus:ring-primary/20 min-h-10 flex-1 resize-none rounded-lg border border-neutral-800 bg-[#0F0F11] px-3 py-2 text-sm text-neutral-200 transition-colors outline-none placeholder:text-neutral-500 focus:ring-2"
        />
        <Button
          type="submit"
          size="sm"
          disabled={loading || !input.trim()}
          className="h-10 rounded-lg"
        >
          {loading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <SendHorizontal className="h-4 w-4" />
          )}
        </Button>
      </form>
    </div>
  )
}
