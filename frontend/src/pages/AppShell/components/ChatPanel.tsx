import { useState, useEffect, useCallback, useMemo, type ReactNode } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
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
import { useChatStore } from '@/store/chatStore'
import { useTaskStore } from '@/store/taskStore'
import {
  askQuestion, askQuestionStream,
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

function SourceBadges({ sources }: { sources: ChatSource[] }) {
  const [expanded, setExpanded] = useState(false)

  if (!sources || sources.length === 0) return null

  return (
    <div className="mt-1.5">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1 text-xs text-neutral-500 transition-colors hover:text-neutral-300"
      >
        <BookOpen className="h-3 w-3" />
        <span>引用来源 ({sources.length})</span>
        {expanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
      </button>
      {expanded && (
        <div className="mt-1 flex flex-wrap gap-1">
          {sources.map((s, i) => (
            <Badge
              key={i}
              variant="outline"
              className="border-neutral-700 bg-neutral-900/60 text-xs font-normal text-neutral-300"
            >
              {s.source_type === 'markdown'
                ? s.section_title || '笔记'
                : `${(s.start_time ?? 0).toFixed(0)}s ~ ${(s.end_time ?? 0).toFixed(0)}s`}
            </Badge>
          ))}
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

  const rawMessages = useChatStore(state => state.chatHistory?.[taskId])
  const messages = useMemo(
    () =>
      Array.isArray(rawMessages)
        ? rawMessages
            .filter(msg => msg && (msg.role === 'user' || msg.role === 'assistant'))
            .map(msg => ({
              ...msg,
              content: typeof msg.content === 'string' ? msg.content : String(msg.content ?? ''),
              sources: Array.isArray(msg.sources) ? msg.sources : undefined,
            }))
        : [],
    [rawMessages]
  )
  const addMessage = useChatStore(state => state.addMessage)
  const updateLastMessage = useChatStore(state => state.updateLastMessage)
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
      let history = messages.map(m => ({ role: m.role, content: m.content }))

      try {
        const res = await askQuestion({
          task_id: taskId,
          video_id: videoId,
          question,
          history,
          provider_id: providerId,
          model_name: modelName,
        })
        addMessage(taskId, {
          role: 'assistant',
          content: res.answer,
          sources: res.sources,
        })
      } catch {
        toast.error('问答请求失败')
      } finally {
        setLoading(false)
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
            首次使用需下载 Embedding 模型（约 80MB），请耐心等待
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
        {messages.length === 0 && !loading ? (
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
            {messages.map((msg, index) => {
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
                    className={`max-w-[82%] rounded-xl px-3 py-2 text-sm ${
                      isUser
                        ? 'bg-primary text-white'
                        : 'border border-neutral-800 bg-[#202024] text-neutral-200 shadow-sm'
                    }`}
                  >
                    {isUser ? (
                      <p className="break-words whitespace-pre-wrap">{msg.content}</p>
                    ) : (
                      <div className="markdown-body prose prose-sm prose-invert prose-headings:my-2 prose-p:my-1 prose-li:my-0.5 max-w-none">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                      </div>
                    )}
                    {msg.role === 'assistant' && Array.isArray(msg.sources) && (
                      <SourceBadges sources={msg.sources} />
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
            {loading && (
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
