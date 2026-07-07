import {
  lazy,
  Suspense,
  type KeyboardEvent,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import { toast } from 'react-hot-toast'
import {
  AlertTriangle,
  ArrowLeftRight,
  Bot,
  CheckCircle2,
  Columns2,
  Copy,
  Download,
  Eye,
  ExternalLink,
  FileText,
  Loader2,
  MessageSquare,
  Maximize2,
  Pause,
  PenSquare,
  Play,
  Plus,
  RefreshCcw,
  Save,
  Share,
  Subtitles,
  Undo2,
  Video,
  X,
} from 'lucide-react'
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from '@/components/ui/resizable'
import { cn } from '@/lib/utils'
import type { Task } from '@/store/taskStore'
import { useTaskStore } from '@/store/taskStore'
import { getTaskLogs, type TaskLogItem } from '@/services/task'
import { resolveVideoPlayer, type VideoPlayerSource } from '@/services/video'
import {
  formatDate,
  formatTime,
  getLatestMarkdown,
  getTaskAuthor,
  getTaskCoverUrl,
  getTaskTitle,
  groupSegments,
} from './utils'
import MarkdownRenderer from './components/MarkdownRenderer'

const MarkmapEditor = lazy(() => import('./components/MarkmapComponent'))
const ChatPanel = lazy(() => import('./components/ChatPanel'))
type MediaPanelMode = 'video-chat' | 'chat-only'

interface WorkspaceViewProps {
  task: Task | null
  openTasks: Task[]
  activeTaskId: string | null
  onSelectTask: (taskId: string) => void
  onCloseTask: (taskId: string) => void
  onNewTask: () => void
}

const statusLabel: Record<string, string> = {
  PENDING: '排队中',
  PARSING: '解析链接',
  DOWNLOADING: '下载音频',
  TRANSCRIBING: '转写文字',
  SUMMARIZING: '总结内容',
  FORMATTING: '整理格式',
  SAVING: '保存结果',
  SUCCESS: '总结完成',
  FAILED: '生成失败',
  RUNNING: '处理中',
}

const PREVIEW_VIDEO_SOURCE_URL = 'https://www.bilibili.com/video/BV1aeLqzUE6L/'
const PREVIEW_VIDEO_BVID = 'BV1aeLqzUE6L'
const PREVIEW_VIDEO_EMBED_URL = `https://player.bilibili.com/player.html?bvid=${PREVIEW_VIDEO_BVID}&page=1&high_quality=1&autoplay=0`

function getStatusDotClass(status: Task['status']) {
  if (status === 'SUCCESS') return 'bg-primary'
  if (status === 'FAILED') return 'bg-red-400'
  return 'bg-amber-400'
}

function createPreviewTask(
  id: string,
  title: string,
  summary: string,
  transcriptLines: string[],
  status: Task['status'] = 'SUCCESS'
): Task {
  const createdAt = new Date().toISOString()
  const segments = transcriptLines.map((text, index) => ({
    start: index * 15,
    end: index * 15 + 12,
    text,
  }))

  return {
    id,
    status,
    markdown: [
      {
        ver_id: `${id}-v1`,
        content: summary,
        style: 'minimal',
        model_name: 'preview',
        created_at: createdAt,
      },
    ],
    transcript: {
      full_text: transcriptLines.join(' '),
      language: 'zh-CN',
      raw: null,
      segments,
    },
    audioMeta: {
      cover_url: '',
      duration: 360,
      file_path: '',
      platform: 'bilibili',
      source_url: PREVIEW_VIDEO_SOURCE_URL,
      player_url: PREVIEW_VIDEO_SOURCE_URL,
      embed_url: PREVIEW_VIDEO_EMBED_URL,
      raw_info: {
        uploader: '示例作者',
        bvid: PREVIEW_VIDEO_BVID,
        source_url: PREVIEW_VIDEO_SOURCE_URL,
        player_url: PREVIEW_VIDEO_SOURCE_URL,
        embed_url: PREVIEW_VIDEO_EMBED_URL,
      },
      title,
      video_id: id,
    },
    createdAt,
    formData: {
      video_url: PREVIEW_VIDEO_SOURCE_URL,
      link: true,
      screenshot: false,
      platform: 'bilibili',
      quality: '1080p',
      model_name: 'preview',
      provider_id: 'preview',
      format: ['summary', 'toc'],
      style: 'minimal',
    },
  }
}

const PREVIEW_TASKS: Task[] = [
  createPreviewTask(
    'preview-note-a',
    '示例笔记 A',
    `# 标签效果预览

打开多个笔记后，它们会留在顶部标签栏里。

## 可以验证的点

- 切换不同笔记
- 关闭当前标签
- 保留最近打开记录
`,
    ['这是第一段示例字幕。', '它用于确认标签切换效果。', '关闭后会回退到相邻标签。']
  ),
  createPreviewTask(
    'preview-note-b',
    '示例笔记 B',
    `# 第二个示例

这条示例笔记用来演示多个标签同时存在时的切换效果。

> 前端开发阶段，这比等后端数据更直观。
`,
    ['第二条示例字幕。', '它会作为另一个标签存在。'],
    'RUNNING'
  ),
  createPreviewTask(
    'preview-note-c',
    '失败任务预览',
    `# 失败态预览

这条 mock 用来确认标签栏里的失败状态、关闭回退和右侧信息栏。
`,
    ['第三条示例字幕。', '这里模拟任务失败时仍保留在工作区标签。'],
    'FAILED'
  ),
]

function WorkspaceTabs({
  tasks,
  activeTaskId,
  onSelectTask,
  onCloseTask,
  onNewTask,
}: {
  tasks: Task[]
  activeTaskId: string | null
  onSelectTask: (taskId: string) => void
  onCloseTask: (taskId: string) => void
  onNewTask: () => void
}) {
  return (
    <div className="flex h-12 shrink-0 items-center border-b border-neutral-800 bg-[#101010]">
      <div
        role="tablist"
        aria-label="已打开笔记"
        className="custom-scrollbar flex min-w-0 flex-1 items-end gap-1 overflow-x-auto px-3 pt-2"
      >
        {tasks.length > 0 ? (
          tasks.map(openTask => {
            const active = openTask.id === activeTaskId
            const title = getTaskTitle(openTask)
            return (
              <div
                key={openTask.id}
                className={`group flex h-9 max-w-[240px] min-w-[150px] shrink-0 items-center rounded-t-lg border px-2 transition-colors ${
                  active
                    ? 'border-neutral-700 border-b-[#111111] bg-[#111111] text-neutral-100'
                    : 'border-transparent bg-[#181818] text-neutral-400 hover:bg-[#202020] hover:text-neutral-200'
                }`}
              >
                <button
                  type="button"
                  role="tab"
                  aria-selected={active}
                  onClick={() => onSelectTask(openTask.id)}
                  className="flex min-w-0 flex-1 items-center gap-2 text-left"
                  title={title}
                >
                  <span
                    className={`h-2 w-2 shrink-0 rounded-full ${getStatusDotClass(openTask.status)}`}
                  />
                  <span className="truncate text-sm font-medium">{title}</span>
                </button>
                <button
                  type="button"
                  onClick={event => {
                    event.stopPropagation()
                    onCloseTask(openTask.id)
                  }}
                  className={`ml-2 flex h-6 w-6 shrink-0 items-center justify-center rounded-md transition-colors hover:bg-neutral-700 hover:text-neutral-100 ${
                    active ? 'text-neutral-400' : 'text-neutral-600 group-hover:text-neutral-400'
                  }`}
                  aria-label={`关闭 ${title}`}
                  title="关闭"
                >
                  <X size={14} />
                </button>
              </div>
            )
          })
        ) : (
          <div className="flex h-9 items-center px-3 text-sm font-medium text-neutral-500">
            工作区
          </div>
        )}
      </div>

      <div className="flex h-full shrink-0 items-center gap-2 border-l border-neutral-800 px-3">
        <button
          type="button"
          onClick={onNewTask}
          className="flex h-8 w-8 items-center justify-center rounded-lg text-neutral-400 transition-colors hover:bg-neutral-800 hover:text-neutral-100"
          aria-label="新建总结"
          title="新建总结"
        >
          <Plus size={17} />
        </button>
      </div>
    </div>
  )
}

function EmptyWorkspace({
  onNewTask,
  onPreviewDemo,
}: {
  onNewTask: () => void
  onPreviewDemo?: () => void
}) {
  return (
    <div className="flex h-full flex-1 flex-col items-center justify-center bg-[#111111]">
      <div className="mb-6 flex h-20 w-20 items-center justify-center rounded-full bg-neutral-800/50">
        <FileText size={32} className="text-neutral-500" />
      </div>
      <h2 className="mb-2 text-xl font-medium text-neutral-300">开始生成笔记</h2>
      <p className="max-w-sm text-center text-sm text-neutral-500">
        输入 Bilibili 视频链接后，AI 会自动抓取内容并生成结构化总结。
      </p>
      <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
        <button
          type="button"
          onClick={onNewTask}
          className="rounded-lg bg-neutral-200 px-5 py-2 text-sm font-bold text-black transition-colors hover:bg-white"
        >
          新建总结
        </button>
        {onPreviewDemo && (
          <button
            type="button"
            onClick={onPreviewDemo}
            className="flex items-center gap-2 rounded-lg border border-neutral-700 bg-[#161616] px-4 py-2 text-sm font-medium text-neutral-200 transition-colors hover:border-neutral-500 hover:bg-[#1B1B1B]"
          >
            <Eye size={14} />
            预览标签效果
          </button>
        )}
      </div>
    </div>
  )
}

function StatusBlock({ task }: { task: Task }) {
  const isFailed = task.status === 'FAILED'
  const isSuccess = task.status === 'SUCCESS'
  const label = statusLabel[task.status] || task.status
  const [logs, setLogs] = useState<TaskLogItem[]>([])
  const retryTask = useTaskStore(state => state.retryTask)

  useEffect(() => {
    if (isSuccess) return
    let cancelled = false

    getTaskLogs(task.id, { page: 1, page_size: 5 }, { silent: true })
      .then(res => {
        if (!cancelled) setLogs(res.items || [])
      })
      .catch(() => {
        if (!cancelled) setLogs([])
      })

    return () => {
      cancelled = true
    }
  }, [isSuccess, task.id])

  if (isSuccess) return null

  return (
    <div className="flex h-full flex-col items-center justify-center gap-4 bg-[#111111] px-6 text-center">
      {isFailed ? (
        <div className="flex h-14 w-14 items-center justify-center rounded-full bg-red-500/10 text-red-400">
          <RefreshCcw size={26} />
        </div>
      ) : (
        <Loader2 className="text-primary h-8 w-8 animate-spin" />
      )}
      <div>
        <p className={`text-lg font-bold ${isFailed ? 'text-red-400' : 'text-neutral-200'}`}>
          {label}
        </p>
        <p className="mt-2 text-sm text-neutral-500">
          {isFailed ? task.message || '请检查后端日志或稍后重试。' : '任务正在执行，完成后会自动刷新。'}
        </p>
      </div>
      {isFailed && (
        <button
          type="button"
          onClick={() => retryTask(task.id)}
          className="flex items-center gap-1.5 rounded-lg border border-red-400/30 bg-red-500/10 px-4 py-2 text-sm font-medium text-red-200 transition-colors hover:bg-red-500/20"
        >
          <RefreshCcw size={15} />
          重试生成
        </button>
      )}
      {logs.length > 0 && (
        <div className="w-full max-w-xl rounded-xl border border-neutral-800 bg-[#161616] p-4 text-left">
          <div className="mb-3 text-xs font-medium text-neutral-500">后端任务日志</div>
          <div className="space-y-2">
            {logs.map((log, index) => (
              <div
                key={log.id || `${log.created_at}-${index}`}
                className="text-xs text-neutral-400"
              >
                <span className="mr-2 font-mono text-neutral-600">
                  {formatDate(log.created_at)}
                </span>
                <span className="mr-2 rounded bg-neutral-800 px-1.5 py-0.5 text-[10px] text-neutral-300">
                  {log.level}
                </span>
                <span>{log.message}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function MindmapFallback() {
  return (
    <div className="flex h-full w-full items-center justify-center bg-[#111111] px-6">
      <div className="w-full max-w-2xl rounded-2xl border border-neutral-800 bg-[#151515] p-6 shadow-2xl">
        <div className="mb-5 flex items-center justify-between">
          <div>
            <div className="h-4 w-24 animate-pulse rounded bg-neutral-800" />
            <div className="mt-2 h-3 w-40 animate-pulse rounded bg-neutral-800/60" />
          </div>
          <div className="h-8 w-24 animate-pulse rounded-lg bg-neutral-800" />
        </div>
        <div className="relative h-56 overflow-hidden rounded-xl border border-neutral-800/70 bg-[#0D0D0D]">
          <div className="bg-primary/20 absolute top-1/2 left-1/2 h-10 w-40 -translate-x-1/2 -translate-y-1/2 animate-pulse rounded-full" />
          <div className="absolute top-[22%] left-[18%] h-7 w-28 animate-pulse rounded-full bg-neutral-800" />
          <div className="absolute top-[28%] right-[16%] h-7 w-32 animate-pulse rounded-full bg-neutral-800" />
          <div className="absolute bottom-[24%] left-[24%] h-7 w-36 animate-pulse rounded-full bg-neutral-800" />
          <div className="absolute right-[24%] bottom-[18%] h-7 w-24 animate-pulse rounded-full bg-neutral-800" />
        </div>
      </div>
    </div>
  )
}

function ChatPanelFallback() {
  return (
    <div className="flex min-h-0 flex-1 flex-col bg-[#161616]">
      <div className="flex-1 space-y-4 overflow-hidden p-4">
        <div className="mr-12 space-y-2 rounded-xl bg-[#202020] p-3">
          <div className="h-3 w-28 animate-pulse rounded bg-neutral-700" />
          <div className="h-3 w-full animate-pulse rounded bg-neutral-700/70" />
        </div>
        <div className="bg-primary/10 ml-12 space-y-2 rounded-xl p-3">
          <div className="bg-primary/30 h-3 w-32 animate-pulse rounded" />
          <div className="bg-primary/20 h-3 w-4/5 animate-pulse rounded" />
        </div>
      </div>
      <div className="border-t border-neutral-800 p-4">
        <div className="h-10 animate-pulse rounded-xl bg-neutral-800" />
      </div>
    </div>
  )
}

function useWorkspaceSplitDirection(): 'horizontal' | 'vertical' {
  const getDirection = () => {
    if (typeof window === 'undefined') return 'horizontal'
    return window.matchMedia('(max-width: 1024px)').matches ? 'vertical' : 'horizontal'
  }

  const [direction, setDirection] = useState<'horizontal' | 'vertical'>(getDirection)

  useEffect(() => {
    if (typeof window === 'undefined') return

    const query = window.matchMedia('(max-width: 1024px)')
    const updateDirection = () => setDirection(query.matches ? 'vertical' : 'horizontal')

    updateDirection()
    query.addEventListener('change', updateDirection)
    return () => query.removeEventListener('change', updateDirection)
  }, [])

  return direction
}

function MediaPanelIconButton({
  title,
  onClick,
  children,
}: {
  title: string
  onClick: () => void
  children: ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      aria-label={title}
      className="flex h-7 w-7 items-center justify-center rounded-md text-neutral-500 transition-colors hover:bg-neutral-800 hover:text-neutral-100"
    >
      {children}
    </button>
  )
}

function MediaPanelControls({
  mode,
  onModeChange,
  onSwapPanels,
}: {
  mode: MediaPanelMode
  onModeChange: (mode: MediaPanelMode) => void
  onSwapPanels: () => void
}) {
  const videoHidden = mode === 'chat-only'

  return (
    <>
      <MediaPanelIconButton title="左右互换" onClick={onSwapPanels}>
        <ArrowLeftRight size={15} />
      </MediaPanelIconButton>
      <MediaPanelIconButton
        title={videoHidden ? '显示视频区域' : '关闭视频区域'}
        onClick={() => onModeChange(videoHidden ? 'video-chat' : 'chat-only')}
      >
        {videoHidden ? <Video size={15} /> : <X size={15} />}
      </MediaPanelIconButton>
    </>
  )
}

function MediaChatHeader({ title, controls }: { title: string; controls: ReactNode }) {
  return (
    <div className="flex h-11 shrink-0 items-center justify-between border-b border-neutral-800/90 bg-[#171719] px-3">
      <span className="flex items-center gap-2 text-sm font-medium text-neutral-200">
        <MessageSquare className="text-primary h-4 w-4" />
        {title}
      </span>
      <div className="flex items-center gap-1.5">{controls}</div>
    </div>
  )
}

function WorkspaceScrollArea({
  active,
  className,
  children,
}: {
  active: boolean
  className?: string
  children: ReactNode
}) {
  const viewportRef = useRef<HTMLDivElement>(null)
  const thumbRef = useRef<HTMLDivElement>(null)
  const frameRef = useRef<number | null>(null)
  const dragStateRef = useRef<{
    pointerId: number
    startY: number
    startScrollTop: number
    scrollPerPixel: number
  } | null>(null)
  const previousUserSelectRef = useRef('')
  const previousCursorRef = useRef('')

  const getThumbMetrics = useCallback(() => {
    const viewport = viewportRef.current
    if (!viewport) return null

    if (viewport.clientHeight <= 0 || viewport.scrollHeight <= 0) return null

    const maxScrollTop = viewport.scrollHeight - viewport.clientHeight
    const trackPadding = 10
    const trackHeight = Math.max(0, viewport.clientHeight - trackPadding * 2)
    if (trackHeight <= 0) return null

    const thumbHeight = Math.min(
      trackHeight,
      Math.max(42, (viewport.clientHeight / viewport.scrollHeight) * trackHeight)
    )
    const maxThumbTop = Math.max(0, trackHeight - thumbHeight)

    return {
      maxScrollTop,
      maxThumbTop,
      thumbHeight,
      trackHeight,
      trackPadding,
    }
  }, [])

  const updateThumb = useCallback(() => {
    frameRef.current = null

    const viewport = viewportRef.current
    const thumb = thumbRef.current
    if (!viewport || !thumb) return

    const metrics = getThumbMetrics()
    if (!metrics || !active || metrics.maxScrollTop <= 2 || viewport.clientHeight <= 0) {
      thumb.style.opacity = '0'
      return
    }

    const thumbTop =
      metrics.trackPadding +
      (viewport.scrollTop / metrics.maxScrollTop) * metrics.maxThumbTop

    thumb.style.height = `${metrics.thumbHeight}px`
    thumb.style.opacity = '0.72'
    thumb.style.transform = `translate3d(0, ${thumbTop}px, 0)`
  }, [active, getThumbMetrics])

  const scheduleThumbUpdate = useCallback(() => {
    if (frameRef.current !== null) return
    frameRef.current = window.requestAnimationFrame(updateThumb)
  }, [updateThumb])

  const restoreDragDocumentState = useCallback(() => {
    document.body.style.userSelect = previousUserSelectRef.current
    document.body.style.cursor = previousCursorRef.current
  }, [])

  const handleThumbPointerDown = useCallback(
    (event: ReactPointerEvent<HTMLDivElement>) => {
      if (event.button !== 0) return

      const viewport = viewportRef.current
      const metrics = getThumbMetrics()
      if (!viewport || !metrics || metrics.maxScrollTop <= 2 || metrics.maxThumbTop <= 0) return

      event.preventDefault()
      event.stopPropagation()
      event.currentTarget.setPointerCapture(event.pointerId)

      previousUserSelectRef.current = document.body.style.userSelect
      previousCursorRef.current = document.body.style.cursor
      document.body.style.userSelect = 'none'
      document.body.style.cursor = 'grabbing'

      dragStateRef.current = {
        pointerId: event.pointerId,
        startY: event.clientY,
        startScrollTop: viewport.scrollTop,
        scrollPerPixel: metrics.maxScrollTop / metrics.maxThumbTop,
      }
    },
    [getThumbMetrics]
  )

  const handleThumbPointerMove = useCallback(
    (event: ReactPointerEvent<HTMLDivElement>) => {
      const dragState = dragStateRef.current
      const viewport = viewportRef.current
      const metrics = getThumbMetrics()
      if (!dragState || !viewport || !metrics || event.pointerId !== dragState.pointerId) return

      event.preventDefault()
      event.stopPropagation()

      const nextScrollTop =
        dragState.startScrollTop + (event.clientY - dragState.startY) * dragState.scrollPerPixel
      viewport.scrollTop = Math.max(0, Math.min(metrics.maxScrollTop, nextScrollTop))
      scheduleThumbUpdate()
    },
    [getThumbMetrics, scheduleThumbUpdate]
  )

  const handleThumbPointerUp = useCallback(
    (event: ReactPointerEvent<HTMLDivElement>) => {
      const dragState = dragStateRef.current
      if (!dragState || event.pointerId !== dragState.pointerId) return

      event.preventDefault()
      event.stopPropagation()
      dragStateRef.current = null
      if (event.currentTarget.hasPointerCapture(event.pointerId)) {
        event.currentTarget.releasePointerCapture(event.pointerId)
      }
      restoreDragDocumentState()
      scheduleThumbUpdate()
    },
    [restoreDragDocumentState, scheduleThumbUpdate]
  )

  const handleTrackPointerDown = useCallback(
    (event: ReactPointerEvent<HTMLDivElement>) => {
      if (event.button !== 0 || event.target === thumbRef.current) return

      const viewport = viewportRef.current
      const metrics = getThumbMetrics()
      const track = event.currentTarget.getBoundingClientRect()
      if (!viewport || !metrics || metrics.maxScrollTop <= 2 || metrics.maxThumbTop <= 0) return

      event.preventDefault()
      event.stopPropagation()

      const clickY = event.clientY - track.top - metrics.trackPadding - metrics.thumbHeight / 2
      const scrollRatio = Math.max(0, Math.min(metrics.maxThumbTop, clickY)) / metrics.maxThumbTop
      viewport.scrollTop = scrollRatio * metrics.maxScrollTop
      scheduleThumbUpdate()
    },
    [getThumbMetrics, scheduleThumbUpdate]
  )

  useEffect(() => {
    if (!active) return

    const viewport = viewportRef.current
    if (!viewport) return

    scheduleThumbUpdate()

    const resizeObserver = new ResizeObserver(scheduleThumbUpdate)
    resizeObserver.observe(viewport)
    if (viewport.firstElementChild) {
      resizeObserver.observe(viewport.firstElementChild)
    }
    window.addEventListener('resize', scheduleThumbUpdate)

    return () => {
      resizeObserver.disconnect()
      window.removeEventListener('resize', scheduleThumbUpdate)
      if (frameRef.current !== null) {
        window.cancelAnimationFrame(frameRef.current)
        frameRef.current = null
      }
      if (dragStateRef.current) {
        dragStateRef.current = null
        restoreDragDocumentState()
      }
    }
  }, [active, restoreDragDocumentState, scheduleThumbUpdate])

  return (
    <div className={cn('absolute inset-y-0 right-4 left-0', active ? 'block' : 'hidden')}>
      <div
        ref={viewportRef}
        onScroll={scheduleThumbUpdate}
        className={cn('workspace-scrollbar h-full overflow-y-auto', className)}
      >
        {children}
      </div>
      <div
        aria-hidden
        onPointerDown={handleTrackPointerDown}
        className="absolute inset-y-0 right-0 w-3"
      >
        <div
          ref={thumbRef}
          onPointerDown={handleThumbPointerDown}
          onPointerMove={handleThumbPointerMove}
          onPointerUp={handleThumbPointerUp}
          onPointerCancel={handleThumbPointerUp}
          className="absolute top-0 right-0 w-1.5 cursor-grab rounded-full bg-neutral-500/75 opacity-0 shadow-[0_0_0_1px_rgba(0,0,0,0.28)] transition-[opacity,background-color] duration-150 hover:bg-neutral-300/85 active:cursor-grabbing"
        />
      </div>
    </div>
  )
}

function SummaryContent({ task }: { task: Task }) {
  const [activeTab, setActiveTab] = useState<'summary' | 'deep-reading' | 'transcript' | 'mindmap'>(
    'summary'
  )
  const [isEditing, setIsEditing] = useState(false)
  const [editorMode, setEditorMode] = useState<'write' | 'split' | 'preview'>('split')
  const [draftContent, setDraftContent] = useState('')
  const [expandedGroups, setExpandedGroups] = useState<Record<number, boolean>>({})
  const retryTask = useTaskStore(state => state.retryTask)
  const updateTaskContent = useTaskStore(state => state.updateTaskContent)
  const { content, version } = getLatestMarkdown(task.markdown)
  const segments = useMemo(() => task.transcript?.segments || [], [task.transcript?.segments])
  const segmentGroups = useMemo(() => groupSegments(segments, 8), [segments])
  const title = getTaskTitle(task)
  const isPreviewTask = task.formData.provider_id === 'preview'
  const markdownContent = isEditing ? draftContent : content
  const isDirty = draftContent !== content
  const draftStats = useMemo(
    () => ({
      chars: draftContent.length,
      lines: draftContent ? draftContent.split(/\r\n|\r|\n/).length : 0,
    }),
    [draftContent]
  )

  useEffect(() => {
    setDraftContent(content)
    setEditorMode('split')
    setIsEditing(false)
  }, [content, task.id])

  const handleStartEditing = () => {
    setDraftContent(content)
    setEditorMode('split')
    setActiveTab('summary')
    setIsEditing(true)
  }

  const handleDiscardEdit = () => {
    setDraftContent(content)
    setIsEditing(false)
    if (isDirty) toast('已放弃未保存修改')
  }

  const handleSaveEdit = () => {
    if (!isDirty) {
      setIsEditing(false)
      return
    }

    if (isPreviewTask) {
      toast('预览模式下不会保存')
      return
    }

    updateTaskContent(task.id, { markdown: draftContent })
    setIsEditing(false)
    toast.success('已保存 Markdown 版本')
  }

  const handleEditorKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
      event.preventDefault()
      handleSaveEdit()
    }
  }

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(
        activeTab === 'transcript'
          ? segments.map(segment => `[${formatTime(segment.start)}] ${segment.text}`).join('\n')
          : markdownContent
      )
      toast.success('已复制到剪贴板')
    } catch {
      toast.error('复制失败')
    }
  }

  const handleDownload = () => {
    const body =
      activeTab === 'transcript'
        ? segments.map(segment => `[${formatTime(segment.start)}] ${segment.text}`).join('\n')
        : markdownContent
    const blob = new Blob([body], { type: 'text/markdown;charset=utf-8' })
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = `${title || 'note'}${activeTab === 'transcript' ? '-transcript' : ''}.md`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(link.href)
  }

  const renderMarkdownEditor = () => {
    if (!isEditing) {
      return (
        <div className="min-h-full w-full rounded-lg border border-neutral-800/80 bg-[#141416] px-4 py-4 shadow-[0_18px_60px_rgba(0,0,0,0.24)]">
          <MarkdownRenderer value={content} emptyPlaceholder="暂无总结内容" />
        </div>
      )
    }

    const editorPane = (
      <textarea
        value={draftContent}
        onChange={event => setDraftContent(event.target.value)}
        onKeyDown={handleEditorKeyDown}
        spellCheck={false}
        className="custom-scrollbar focus:border-primary/70 focus:ring-primary/20 h-full w-full resize-none rounded-lg border border-neutral-800 bg-[#0A0A0A] px-4 py-3 font-mono text-sm leading-6 text-neutral-100 transition-colors outline-none placeholder:text-neutral-600 focus:ring-2"
        placeholder="# 开始编辑 Markdown"
      />
    )

    const previewPane = (
      <div className="custom-scrollbar h-full overflow-y-auto rounded-lg border border-neutral-800/80 bg-[#141416] px-5 py-4">
        <MarkdownRenderer value={draftContent} emptyPlaceholder="预览内容为空" />
      </div>
    )

    return (
      <div className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-neutral-800 bg-[#151515] px-3 py-2">
          <div className="flex h-8 items-center rounded-md border border-neutral-800 bg-[#0C0C0C] p-0.5">
            {(['write', 'split', 'preview'] as const).map(mode => {
              const active = editorMode === mode
              const Icon = mode === 'write' ? PenSquare : mode === 'split' ? Columns2 : Eye
              const label = mode === 'write' ? '编辑' : mode === 'split' ? '分屏' : '预览'

              return (
                <button
                  key={mode}
                  type="button"
                  onClick={() => setEditorMode(mode)}
                  className={`flex h-7 items-center gap-1.5 rounded px-2.5 text-xs transition-colors ${
                    active
                      ? 'bg-neutral-200 text-black'
                      : 'text-neutral-400 hover:bg-neutral-800 hover:text-neutral-100'
                  }`}
                >
                  <Icon size={13} />
                  {label}
                </button>
              )
            })}
          </div>
          <div className="flex items-center gap-3 text-xs text-neutral-500">
            <span>{draftStats.lines} 行</span>
            <span>{draftStats.chars} 字符</span>
            <span className={isDirty ? 'text-amber-300' : 'text-neutral-500'}>
              {isDirty ? '未保存' : '已同步'}
            </span>
          </div>
        </div>

        <div
          className={
            editorMode === 'split'
              ? 'grid h-[calc(100vh-280px)] min-h-[420px] gap-4 xl:grid-cols-2'
              : 'h-[calc(100vh-280px)] min-h-[420px]'
          }
        >
          {(editorMode === 'write' || editorMode === 'split') && (
            <div className={editorMode === 'split' ? 'min-h-0' : 'h-full'}>{editorPane}</div>
          )}
          {(editorMode === 'preview' || editorMode === 'split') && (
            <div className={editorMode === 'split' ? 'min-h-0' : 'h-full'}>{previewPane}</div>
          )}
        </div>
      </div>
    )
  }

  if (task.status !== 'SUCCESS') {
    return <StatusBlock task={task} />
  }

  return (
    <div className="flex h-full flex-1 flex-col bg-[#111111]">
      <div className="flex h-14 shrink-0 items-center justify-between border-b border-neutral-800 px-4">
        <div className="flex items-center gap-6">
          {[
            ['summary', '全文总结'],
            ['deep-reading', '原文细读'],
            ['transcript', '字幕脚本'],
            ['mindmap', '思维导图'],
          ].map(([key, label]) => (
            <button
              type="button"
              key={key}
              onClick={() => setActiveTab(key as typeof activeTab)}
              className={`h-14 text-sm font-medium transition-colors ${
                activeTab === key
                  ? 'border-primary text-primary border-b-2'
                  : 'text-neutral-400 hover:text-neutral-200'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {activeTab === 'summary' && (
        <>
          <div className="flex h-12 shrink-0 items-center justify-between border-b border-neutral-800/50 bg-[#151515] px-6">
            <div className="flex items-center gap-4 text-sm text-neutral-400">
              <span>章节 ({segmentGroups.length})</span>
              {version && <span className="text-xs">版本 {version.ver_id.slice(-6)}</span>}
              {isEditing && (
                <span
                  className={`rounded border px-2 py-0.5 text-xs ${
                    isDirty
                      ? 'border-amber-400/30 bg-amber-400/10 text-amber-200'
                      : 'border-neutral-700 bg-neutral-800/70 text-neutral-400'
                  }`}
                >
                  {isDirty ? '草稿未保存' : '草稿已同步'}
                </span>
              )}
            </div>
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={handleCopy}
                className="flex items-center gap-1.5 text-xs text-neutral-400 transition-colors hover:text-neutral-200"
              >
                <Copy size={14} />
                复制
              </button>
              <button
                type="button"
                onClick={handleDownload}
                className="flex items-center gap-1.5 text-xs text-neutral-400 transition-colors hover:text-neutral-200"
              >
                <Download size={14} />
                下载
              </button>
              <button
                type="button"
                onClick={() => toast('分享功能稍后接入。')}
                className="flex items-center gap-1.5 text-xs text-pink-500 transition-colors hover:text-pink-400"
              >
                <Share size={14} />
                分享
              </button>
            </div>
          </div>

          <div className="flex shrink-0 items-center justify-between border-b border-neutral-800/40 px-6 py-3">
            <div className="text-primary flex items-center gap-2 text-sm">
              <CheckCircle2 size={16} />
              <span>{statusLabel[task.status]}</span>
            </div>
            <div className="flex items-center gap-4">
              {isEditing ? (
                <>
                  <button
                    type="button"
                    onClick={handleDiscardEdit}
                    className="flex items-center gap-1.5 text-xs text-neutral-400 transition-colors hover:text-neutral-200"
                  >
                    <Undo2 size={14} />
                    放弃
                  </button>
                  <button
                    type="button"
                    onClick={handleSaveEdit}
                    disabled={!isDirty}
                    className="text-primary flex items-center gap-1.5 text-xs transition-colors hover:text-blue-300 disabled:cursor-not-allowed disabled:text-neutral-600"
                  >
                    <Save size={14} />
                    保存版本
                  </button>
                </>
              ) : (
                <button
                  type="button"
                  onClick={handleStartEditing}
                  className="flex items-center gap-1.5 text-xs text-neutral-400 transition-colors hover:text-neutral-200"
                >
                  <PenSquare size={14} />
                  编辑
                </button>
              )}
              <button
                type="button"
                onClick={() => {
                  if (isPreviewTask) {
                    toast('预览模式下不会重新生成')
                    return
                  }
                  retryTask(task.id)
                }}
                className="flex items-center gap-1.5 text-xs text-neutral-400 transition-colors hover:text-neutral-200"
              >
                <RefreshCcw size={14} />
                重新总结
              </button>
            </div>
          </div>
        </>
      )}

      <div className="relative flex-1 overflow-hidden">
        <WorkspaceScrollArea
          active={activeTab === 'summary'}
          className="pt-2 pr-1 pb-8 pl-2"
        >
          <div className="w-full max-w-none">{renderMarkdownEditor()}</div>
        </WorkspaceScrollArea>

        <WorkspaceScrollArea
          active={activeTab === 'deep-reading'}
          className="pt-6 pr-3 pb-20 pl-6"
        >
          <div className="mx-auto max-w-3xl space-y-8">
            <div className="border-b border-neutral-800/50 pb-4">
              <h2 className="text-lg font-bold text-neutral-100">视频主题: {title}</h2>
              <p className="mt-2 text-xs text-neutral-500">按真实字幕片段自动分组展示</p>
            </div>
            {segmentGroups.length > 0 ? (
              segmentGroups.map((group, index) => (
                <div key={`${group.start}-${index}`} className="mb-8">
                  <div className="mb-3 flex items-center justify-between gap-4">
                    <h3 className="flex items-center gap-2 font-medium text-blue-400">
                      <span className="text-primary font-mono">{formatTime(group.start)}</span>
                      <span>{group.text.slice(0, 42) || '字幕片段'}</span>
                    </h3>
                    <button
                      type="button"
                      onClick={() =>
                        setExpandedGroups(prev => ({ ...prev, [index]: !prev[index] }))
                      }
                      className="shrink-0 text-xs text-neutral-400 transition-colors hover:text-neutral-200"
                    >
                      {expandedGroups[index] ? '收起原文' : '展开原文'}
                    </button>
                  </div>
                  <p className="text-sm leading-relaxed text-neutral-300">{group.text}</p>
                  {expandedGroups[index] && (
                    <div className="mt-4 rounded-xl border border-neutral-800/80 bg-[#0A0A0A] p-4">
                      <div className="mb-4 flex items-center gap-2 border-b border-neutral-800 pb-2 text-xs text-neutral-400">
                        <Subtitles size={14} />
                        字幕原文
                      </div>
                      <div className="space-y-4">
                        {group.segments.map(segment => (
                          <div
                            key={`${segment.start}-${segment.text}`}
                            className="flex gap-4 text-sm"
                          >
                            <div className="w-14 shrink-0 font-mono text-blue-400">
                              {formatTime(segment.start)}
                            </div>
                            <div className="leading-relaxed text-neutral-400">{segment.text}</div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ))
            ) : (
              <div className="flex h-32 items-center justify-center rounded-xl border border-dashed border-neutral-800 bg-[#1A1A1A] text-sm text-neutral-600">
                暂无字幕片段
              </div>
            )}
          </div>
        </WorkspaceScrollArea>

        <WorkspaceScrollArea
          active={activeTab === 'transcript'}
          className="pt-6 pr-3 pb-20 pl-6"
        >
          <div className="mx-auto max-w-3xl">
            <div className="mb-6 flex items-center justify-between border-b border-neutral-800/50 pb-4">
              <h2 className="text-lg font-bold text-neutral-100">字幕脚本</h2>
              <button
                type="button"
                onClick={handleCopy}
                className="flex items-center gap-1 text-xs text-neutral-400 transition-colors hover:text-neutral-200"
              >
                <Copy size={14} />
                复制全部
              </button>
            </div>
            <div className="space-y-4 rounded-xl border border-neutral-800/80 bg-[#0A0A0A] p-6">
              {segments.length > 0 ? (
                segments.map(segment => (
                  <div key={`${segment.start}-${segment.text}`} className="flex gap-4 text-sm">
                    <div className="text-primary w-14 shrink-0 font-mono">
                      {formatTime(segment.start)}
                    </div>
                    <div className="leading-relaxed text-neutral-300">{segment.text}</div>
                  </div>
                ))
              ) : (
                <div className="py-10 text-center text-neutral-500">暂无字幕数据</div>
              )}
            </div>
          </div>
        </WorkspaceScrollArea>

        <div className={`absolute inset-0 ${activeTab === 'mindmap' ? 'block' : 'hidden'}`}>
          {activeTab !== 'mindmap' ? null : markdownContent ? (
            <Suspense fallback={<MindmapFallback />}>
              <MarkmapEditor
                value={markdownContent}
                onChange={() => {}}
                height="100%"
                title={title}
              />
            </Suspense>
          ) : (
            <div className="flex h-full items-center justify-center text-sm text-neutral-500">
              暂无可生成思维导图的内容
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function valueFromRecord(value: unknown, key: string): string {
  if (!value || typeof value !== 'object') return ''
  const item = (value as Record<string, unknown>)[key]
  return typeof item === 'string' ? item : ''
}

function nestedValueFromRecord(value: unknown, parentKey: string, childKey: string): string {
  if (!value || typeof value !== 'object') return ''
  const parent = (value as Record<string, unknown>)[parentKey]
  if (!parent || typeof parent !== 'object') return ''
  const item = (parent as Record<string, unknown>)[childKey]
  return typeof item === 'string' ? item : ''
}

function extractBvid(value: string): string {
  return value.match(/BV[0-9A-Za-z]{10}/)?.[0] || ''
}

function isBackendVideoId(value: string): boolean {
  return /^b_BV[0-9A-Za-z]{10}$/.test(value) || /^av_\d+$/.test(value)
}

function getTaskSourceUrl(task: Task | null): string {
  if (!task) return ''
  return (
    task.audioMeta?.source_url ||
    valueFromRecord(task.audioMeta?.raw_info, 'source_url') ||
    nestedValueFromRecord(task.audioMeta?.raw_info, 'backend_video', 'source_url') ||
    nestedValueFromRecord(task.audioMeta?.raw_info, 'backend_video', 'url') ||
    task.formData?.video_url ||
    ''
  )
}

function getTaskVideoId(task: Task | null): string {
  if (!task) return ''
  const rawInfo = task.audioMeta?.raw_info
  const candidates = [
    task.audioMeta?.video_id,
    valueFromRecord(rawInfo, 'video_id'),
    nestedValueFromRecord(rawInfo, 'backend_video', 'video_id'),
    task.id,
  ].filter(Boolean) as string[]

  for (const candidate of candidates) {
    if (isBackendVideoId(candidate)) return candidate
  }

  for (const candidate of candidates) {
    const bvid = extractBvid(candidate)
    if (bvid) return `b_${bvid}`
  }

  const bvid = getTaskBvid(task)
  return bvid ? `b_${bvid}` : ''
}

function getTaskBvid(task: Task | null): string {
  if (!task) return ''
  const sourceUrl = getTaskSourceUrl(task)
  return (
    valueFromRecord(task.audioMeta?.raw_info, 'bvid') ||
    nestedValueFromRecord(task.audioMeta?.raw_info, 'backend_video', 'bvid') ||
    extractBvid(sourceUrl) ||
    ''
  )
}

function getTaskEmbedUrl(task: Task | null): string {
  if (!task) return ''
  const savedEmbed =
    task.audioMeta?.embed_url ||
    valueFromRecord(task.audioMeta?.raw_info, 'embed_url') ||
    nestedValueFromRecord(task.audioMeta?.raw_info, 'backend_video', 'embed_url')
  if (savedEmbed) return savedEmbed

  const bvid = getTaskBvid(task)
  if (!bvid) return ''

  return `https://player.bilibili.com/player.html?bvid=${encodeURIComponent(
    bvid
  )}&page=1&high_quality=1&autoplay=0`
}

function isBilibiliSource(value: string): boolean {
  return /(^https?:\/\/)?([^/]+\.)?(bilibili\.com|b23\.tv)\//i.test(value)
}

function playerErrorMessage(error: unknown): string {
  if (!error || typeof error !== 'object') return '视频播放地址解析失败'
  const record = error as Record<string, unknown>
  const detail = record.detail || record.message || record.msg
  return typeof detail === 'string' ? detail : '视频播放地址解析失败'
}

function isPlayerAuthError(error: unknown): boolean {
  if (!error || typeof error !== 'object') return false
  const record = error as Record<string, unknown>
  return (
    record.status === 401 ||
    record.statusCode === 401 ||
    record.status === 403 ||
    record.statusCode === 403
  )
}

function formatPlayerTime(value: number): string {
  if (!Number.isFinite(value) || value < 0) return '0:00'
  const total = Math.floor(value)
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const seconds = total % 60
  if (hours > 0) {
    return `${hours}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
  }
  return `${minutes}:${String(seconds).padStart(2, '0')}`
}

function TaskVideoPlayer({
  task,
  title,
  coverUrl,
}: {
  task: Task
  title: string
  coverUrl: string
}) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const [playerSource, setPlayerSource] = useState<VideoPlayerSource | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [playerMode, setPlayerMode] = useState<'native' | 'embed'>('native')
  const [playing, setPlaying] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(0)
  const [playbackRate, setPlaybackRate] = useState(1)
  const [subtitlesVisible, setSubtitlesVisible] = useState(true)
  const [reloadKey, setReloadKey] = useState(0)
  const sourceUrl = getTaskSourceUrl(task)
  const videoId = getTaskVideoId(task)
  const fallbackEmbedUrl = getTaskEmbedUrl(task)
  const embedUrl = playerSource?.embed_url || fallbackEmbedUrl
  const posterUrl = playerSource?.cover_url || coverUrl
  const streamUrl = playerSource?.local_stream_url || playerSource?.stream_url || ''
  const quality = task.formData?.quality || '1080p'
  const segments = useMemo(() => task.transcript?.segments || [], [task.transcript?.segments])
  const knownDuration = duration || playerSource?.duration_seconds || task.audioMeta?.duration || 0
  const activeSegment = useMemo(() => {
    return segments.find(segment => currentTime >= segment.start && currentTime < segment.end) || null
  }, [currentTime, segments])
  const timelineMarkers = useMemo(() => {
    const chapters = task.audioMeta?.chapters || []
    if (chapters.length > 0) {
      return chapters
        .map((chapter, index) => ({
          key: `chapter-${index}`,
          title: chapter.title || `章节 ${index + 1}`,
          time: Number(chapter.start_time || 0),
        }))
        .filter(marker => marker.time >= 0)
    }

    return segments
      .filter((_, index) => index % 8 === 0)
      .map((segment, index) => ({
        key: `segment-${index}`,
        title: segment.text,
        time: segment.start,
      }))
  }, [segments, task.audioMeta?.chapters])

  useEffect(() => {
    let cancelled = false

    setPlayerSource(null)
    setError('')
    setPlayerMode('native')
    setCurrentTime(0)
    setDuration(0)
    setPlaying(false)

    if (!sourceUrl) {
      setError('当前笔记缺少视频链接')
      return
    }

    if (!isBilibiliSource(sourceUrl)) {
      setError('当前内置播放器暂只支持 Bilibili 链接')
      return
    }

    setLoading(true)
    resolveVideoPlayer(sourceUrl, quality, videoId, { silent: true })
      .then(data => {
        if (cancelled) return
        setPlayerSource(data)
        const hasNativeSource = Boolean(data.local_stream_url || data.stream_url)
        setPlayerMode(hasNativeSource ? 'native' : 'embed')
        if (!hasNativeSource && !(data.embed_url || fallbackEmbedUrl)) {
          setError('暂无可播放视频源')
        }
      })
      .catch(err => {
        if (cancelled) return
        setError(playerErrorMessage(err))
        setPlayerMode(!isPlayerAuthError(err) && fallbackEmbedUrl ? 'embed' : 'native')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [fallbackEmbedUrl, quality, reloadKey, sourceUrl, videoId])

  useEffect(() => {
    const video = videoRef.current
    if (!video) return
    video.playbackRate = playbackRate
  }, [playbackRate, streamUrl])

  const handleRetry = () => {
    setReloadKey(value => value + 1)
  }

  const togglePlay = () => {
    const video = videoRef.current
    if (!video) return
    if (video.paused) {
      void video.play()
    } else {
      video.pause()
    }
  }

  const seekTo = (value: number) => {
    const video = videoRef.current
    if (!video) return
    video.currentTime = value
    setCurrentTime(value)
  }

  const requestFullscreen = () => {
    const host = videoRef.current?.parentElement
    if (host?.requestFullscreen) {
      void host.requestFullscreen()
    }
  }

  const canUseNative = Boolean(streamUrl)
  const canUseEmbed = Boolean(embedUrl)
  const canShowEmbed = playerMode === 'embed' && canUseEmbed
  const canShowVideo = playerMode === 'native' && canUseNative

  return (
    <div className="relative aspect-video shrink-0 overflow-hidden border-b border-neutral-800 bg-black">
      <div className="absolute top-3 left-3 z-20 flex items-center gap-1 rounded-full bg-black/70 p-1 text-xs text-neutral-200 backdrop-blur-sm">
        <button
          type="button"
          onClick={() => setPlayerMode('native')}
          disabled={!canUseNative}
          className={`rounded-full px-2.5 py-1 transition-colors disabled:cursor-not-allowed disabled:opacity-45 ${
            playerMode === 'native' ? 'bg-neutral-100 text-neutral-950' : 'hover:bg-neutral-800'
          }`}
        >
          本地
        </button>
        <button
          type="button"
          onClick={() => setPlayerMode('embed')}
          disabled={!canUseEmbed}
          className={`rounded-full px-2.5 py-1 transition-colors disabled:cursor-not-allowed disabled:opacity-45 ${
            playerMode === 'embed' ? 'bg-neutral-100 text-neutral-950' : 'hover:bg-neutral-800'
          }`}
        >
          B站
        </button>
      </div>

      {canShowEmbed ? (
        <iframe
          key={embedUrl}
          src={embedUrl}
          title={title}
          allow="autoplay; fullscreen; picture-in-picture"
          allowFullScreen
          referrerPolicy="no-referrer-when-downgrade"
          className="h-full w-full border-0 bg-black"
        />
      ) : canShowVideo ? (
        <>
          <video
            ref={videoRef}
            key={`${streamUrl}-${reloadKey}`}
            src={streamUrl}
            poster={posterUrl || undefined}
            preload="metadata"
            playsInline
            className="h-full w-full bg-black object-contain"
            onClick={togglePlay}
            onPlay={() => setPlaying(true)}
            onPause={() => setPlaying(false)}
            onLoadedMetadata={event => {
              const mediaDuration = event.currentTarget.duration
              setDuration(Number.isFinite(mediaDuration) ? mediaDuration : 0)
              event.currentTarget.playbackRate = playbackRate
            }}
            onTimeUpdate={event => setCurrentTime(event.currentTarget.currentTime)}
            onError={() => {
              setError('本地播放器加载失败，可切换到 B 站播放器兜底')
              if (embedUrl) setPlayerMode('embed')
            }}
          />

          {!playing && (
            <button
              type="button"
              onClick={togglePlay}
              className="absolute left-1/2 top-1/2 z-10 flex h-16 w-16 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full bg-black/55 text-white backdrop-blur-sm transition-colors hover:bg-black/75"
              aria-label="播放"
            >
              <Play size={30} fill="currentColor" />
            </button>
          )}

          {subtitlesVisible && activeSegment && (
            <div className="pointer-events-none absolute inset-x-6 bottom-20 z-10 flex justify-center">
              <div className="max-w-full rounded-lg bg-black/72 px-3 py-2 text-center text-sm leading-relaxed text-white shadow-2xl backdrop-blur-sm">
                {activeSegment.text}
              </div>
            </div>
          )}

          <div className="absolute inset-x-0 bottom-0 z-20 bg-gradient-to-t from-black/90 via-black/70 to-transparent px-3 pb-3 pt-12">
            <div className="relative mb-2 h-5">
              <div className="absolute left-0 right-0 top-1/2 h-1 -translate-y-1/2 rounded-full bg-white/18" />
              {knownDuration > 0 &&
                timelineMarkers.map(marker => {
                  const left = Math.min(100, Math.max(0, (marker.time / knownDuration) * 100))
                  return (
                    <button
                      key={marker.key}
                      type="button"
                      onClick={() => seekTo(marker.time)}
                      className="absolute top-1/2 z-10 h-3 w-1 -translate-y-1/2 rounded-full bg-emerald-300/80 transition-transform hover:scale-y-125"
                      style={{ left: `${left}%` }}
                      title={`${formatPlayerTime(marker.time)} ${marker.title}`}
                      aria-label={`跳转到 ${formatPlayerTime(marker.time)}`}
                    />
                  )
                })}
              <input
                type="range"
                min={0}
                max={Math.max(knownDuration, currentTime, 1)}
                step={0.1}
                value={currentTime}
                onChange={event => seekTo(Number(event.target.value))}
                className="absolute inset-x-0 top-1/2 h-5 -translate-y-1/2 cursor-pointer appearance-none bg-transparent accent-emerald-300"
                aria-label="视频进度"
              />
            </div>
            <div className="flex items-center gap-2 text-xs text-neutral-100">
              <button
                type="button"
                onClick={togglePlay}
                className="flex h-8 w-8 items-center justify-center rounded-full bg-white/10 transition-colors hover:bg-white/20"
                aria-label={playing ? '暂停' : '播放'}
              >
                {playing ? <Pause size={16} fill="currentColor" /> : <Play size={16} fill="currentColor" />}
              </button>
              <span className="min-w-[74px] font-mono text-[11px] text-neutral-200">
                {formatPlayerTime(currentTime)} / {formatPlayerTime(knownDuration)}
              </span>
              <div className="ml-auto flex items-center gap-1">
                {[0.75, 1, 1.25, 1.5, 2].map(rate => (
                  <button
                    key={rate}
                    type="button"
                    onClick={() => setPlaybackRate(rate)}
                    className={`rounded-md px-2 py-1 text-[11px] transition-colors ${
                      playbackRate === rate ? 'bg-white text-black' : 'bg-white/10 hover:bg-white/20'
                    }`}
                  >
                    {rate}x
                  </button>
                ))}
                <button
                  type="button"
                  onClick={() => setSubtitlesVisible(value => !value)}
                  className={`flex h-7 w-7 items-center justify-center rounded-md transition-colors ${
                    subtitlesVisible ? 'bg-white text-black' : 'bg-white/10 hover:bg-white/20'
                  }`}
                  title={subtitlesVisible ? '隐藏字幕' : '显示字幕'}
                  aria-label={subtitlesVisible ? '隐藏字幕' : '显示字幕'}
                >
                  <Subtitles size={15} />
                </button>
                <button
                  type="button"
                  onClick={requestFullscreen}
                  className="flex h-7 w-7 items-center justify-center rounded-md bg-white/10 transition-colors hover:bg-white/20"
                  title="全屏"
                  aria-label="全屏"
                >
                  <Maximize2 size={15} />
                </button>
              </div>
            </div>
          </div>
        </>
      ) : (
        <div className="absolute inset-0 flex items-center justify-center bg-neutral-950">
          {posterUrl ? (
            <img
              src={posterUrl}
              alt={title}
              referrerPolicy="no-referrer"
              className="absolute inset-0 h-full w-full object-cover opacity-45"
            />
          ) : null}
          <div className="relative z-10 flex flex-col items-center text-neutral-400">
            {loading ? (
              <>
                <Loader2 className="mb-2 h-6 w-6 animate-spin text-neutral-300" />
                <span className="text-xs">正在解析播放地址</span>
              </>
            ) : (
              <>
                <Video size={32} className="mb-2 opacity-45" />
                <span className="text-xs">暂无可播放视频源</span>
              </>
            )}
          </div>
        </div>
      )}

      {loading && (canShowVideo || canShowEmbed) && (
        <div className="absolute top-3 left-3 flex items-center gap-2 rounded-full bg-black/70 px-2.5 py-1 text-xs text-neutral-100 backdrop-blur-sm">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          解析中
        </div>
      )}

      {!loading && (playerSource?.height || playerSource?.ext) && !canShowEmbed && (
        <div className="absolute top-3 left-[108px] z-20 rounded-full bg-black/70 px-2.5 py-1 text-xs text-neutral-100 backdrop-blur-sm">
          {[playerSource.height ? `${playerSource.height}p` : '', playerSource.ext?.toUpperCase()]
            .filter(Boolean)
            .join(' · ')}
        </div>
      )}

      {sourceUrl && (
        <a
          href={sourceUrl}
          target="_blank"
          rel="noreferrer"
          className="absolute top-3 right-3 flex h-8 w-8 items-center justify-center rounded-full bg-black/70 text-neutral-200 backdrop-blur-sm transition-colors hover:bg-neutral-800 hover:text-white"
          title="打开原视频"
          aria-label="打开原视频"
        >
          <ExternalLink size={15} />
        </a>
      )}

      {error && !canShowEmbed && (
        <div className="absolute inset-x-4 bottom-4 rounded-lg border border-neutral-700/80 bg-[#111111]/95 p-3 text-sm text-neutral-200 shadow-2xl backdrop-blur">
          <div className="flex gap-2">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-300" />
            <div className="min-w-0 flex-1">
              <p className="line-clamp-2 text-xs leading-5 text-neutral-300">{error}</p>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={handleRetry}
                  className="rounded-md border border-neutral-700 px-2 py-1 text-xs text-neutral-200 transition-colors hover:border-neutral-500 hover:bg-neutral-800"
                >
                  重试
                </button>
                {embedUrl && (
                  <button
                    type="button"
                    onClick={() => setPlayerMode('embed')}
                    className="rounded-md border border-neutral-700 px-2 py-1 text-xs text-neutral-200 transition-colors hover:border-neutral-500 hover:bg-neutral-800"
                  >
                    使用 B 站播放器
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function VideoChatPanel({
  task,
  mode,
  onModeChange,
  onSwapPanels,
}: {
  task: Task | null
  mode: MediaPanelMode
  onModeChange: (mode: MediaPanelMode) => void
  onSwapPanels: () => void
}) {
  const [chatReadyToLoad, setChatReadyToLoad] = useState(false)
  const coverUrl = getTaskCoverUrl(task)
  const title = getTaskTitle(task)
  const author = getTaskAuthor(task)
  const createdAt = formatDate(task?.createdAt)
  const taskId = task?.id
  const taskStatus = task?.status
  const isPreviewTask = task?.formData.provider_id === 'preview'
  const showVideoArea = mode === 'video-chat'
  const chatTitle = showVideoArea ? '视频问答' : 'AI 对话'
  const controls = (
    <MediaPanelControls mode={mode} onModeChange={onModeChange} onSwapPanels={onSwapPanels} />
  )

  useEffect(() => {
    setChatReadyToLoad(false)
    if (!taskId || taskStatus !== 'SUCCESS' || isPreviewTask) return

    const id = window.setTimeout(() => {
      setChatReadyToLoad(true)
    }, 350)

    return () => window.clearTimeout(id)
  }, [isPreviewTask, taskId, taskStatus])

  if (!task) {
    return (
      <div className="flex h-full flex-col bg-[#111111]">
        <MediaChatHeader title={showVideoArea ? '视频与对话' : chatTitle} controls={controls} />
        <div className="flex flex-1 flex-col items-center justify-center">
          <div className="mb-4 text-neutral-700">
            <Video size={48} strokeWidth={1} />
          </div>
          <p className="text-sm text-neutral-500">等待视频载入...</p>
        </div>
      </div>
    )
  }

  if (isPreviewTask) {
    return (
      <div className="flex h-full flex-col bg-[#111111]">
        {showVideoArea && (
          <>
            <div className="relative aspect-video shrink-0 overflow-hidden border-b border-neutral-800 bg-black">
              <div className="absolute inset-0 flex items-center justify-center bg-neutral-900">
                <div className="flex flex-col items-center text-neutral-600">
                  <Video size={32} className="mb-2 opacity-30" />
                  <span className="text-xs">预览模式</span>
                </div>
              </div>
              <div className="absolute top-3 left-3 rounded-full bg-black/70 px-2 py-1 text-xs text-neutral-200 backdrop-blur-sm">
                示例数据
              </div>
            </div>

            <div className="shrink-0 border-b border-neutral-800 p-4">
              <div className="mb-2 flex items-center justify-between gap-4">
                <h3 className="line-clamp-1 text-lg font-bold text-neutral-100">{title}</h3>
                <span className="bg-primary/10 text-primary shrink-0 rounded px-2 py-1 text-xs">
                  预览
                </span>
              </div>
              <div className="flex items-center gap-3">
                {author && <span className="text-primary text-sm font-medium">{author}</span>}
                {createdAt && <span className="text-xs text-neutral-500">{createdAt}</span>}
              </div>
            </div>
          </>
        )}

        <div className="flex min-h-0 flex-1 flex-col overflow-hidden bg-[#151515]">
          <MediaChatHeader title={chatTitle} controls={controls} />
          <div className="flex flex-1 items-center justify-center px-6 text-center text-sm text-neutral-400">
            <div>
              <Bot className="mx-auto mb-3 h-6 w-6 text-neutral-600" />
              {showVideoArea
                ? '这里保留的是演示位，你切换左侧标签时可以看到多个打开记录、关闭回退和空态重现。'
                : '当前已关闭视频区域，只保留 AI 对话面板。预览任务不会连接后端问答。'}
            </div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col bg-[#111111]">
      {showVideoArea && (
        <>
          <TaskVideoPlayer task={task} title={title} coverUrl={coverUrl} />

          <div className="shrink-0 border-b border-neutral-800 p-4">
            <div className="mb-2 flex items-center justify-between gap-4">
              <h3 className="line-clamp-1 text-lg font-bold text-neutral-100">{title}</h3>
              <span
                className={`shrink-0 rounded px-2 py-1 text-xs ${
                  task.status === 'SUCCESS'
                    ? 'bg-primary/10 text-primary'
                    : task.status === 'FAILED'
                      ? 'bg-red-500/10 text-red-400'
                      : 'bg-neutral-800 text-neutral-300'
                }`}
              >
                {statusLabel[task.status] || task.status}
              </span>
            </div>
            <div className="flex items-center gap-3">
              {author && <span className="text-primary text-sm font-medium">{author}</span>}
              {createdAt && <span className="text-xs text-neutral-500">{createdAt}</span>}
            </div>
          </div>
        </>
      )}

      <div className="flex min-h-0 flex-1 flex-col overflow-hidden bg-[#151515]">
        {task.status === 'SUCCESS' ? (
          chatReadyToLoad ? (
            <Suspense
              fallback={
                <div className="flex h-full flex-col overflow-hidden bg-[#151515]">
                  <MediaChatHeader title={chatTitle} controls={controls} />
                  <ChatPanelFallback />
                </div>
              }
            >
              <ChatPanel
                taskId={task.id}
                mode="half"
                onModeChange={() => {}}
                title={chatTitle}
                headerActions={controls}
                showModeToggle={false}
              />
            </Suspense>
          ) : (
            <div className="flex h-full flex-col overflow-hidden bg-[#151515]">
              <MediaChatHeader title={chatTitle} controls={controls} />
              <ChatPanelFallback />
            </div>
          )
        ) : (
          <div className="flex h-full flex-col overflow-hidden bg-[#151515]">
            <MediaChatHeader title={chatTitle} controls={controls} />
            <div className="flex flex-1 items-center justify-center px-6 text-center text-sm text-neutral-500">
              <div>
                <Bot className="mx-auto mb-3 h-6 w-6 text-neutral-600" />
                笔记完成后即可基于视频内容提问。
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

const ENABLE_WORKSPACE_MOCK = import.meta.env.VITE_ENABLE_WORKSPACE_MOCK === 'true'

export default function WorkspaceView({
  task,
  openTasks,
  activeTaskId,
  onSelectTask,
  onCloseTask,
  onNewTask,
}: WorkspaceViewProps) {
  const [previewMode, setPreviewMode] = useState(ENABLE_WORKSPACE_MOCK)
  const [previewOpenTaskIds, setPreviewOpenTaskIds] = useState<string[]>(
    PREVIEW_TASKS.map(previewTask => previewTask.id)
  )
  const [previewActiveTaskId, setPreviewActiveTaskId] = useState(PREVIEW_TASKS[0]?.id || '')
  const [mediaPanelMode, setMediaPanelMode] = useState<MediaPanelMode>('video-chat')
  const [panelsSwapped, setPanelsSwapped] = useState(false)
  const splitDirection = useWorkspaceSplitDirection()
  const isVerticalSplit = splitDirection === 'vertical'
  const hasRealTabs = openTasks.length > 0
  const isPreviewActive = previewMode && !hasRealTabs
  const visibleTasks = isPreviewActive
    ? PREVIEW_TASKS.filter(previewTask => previewOpenTaskIds.includes(previewTask.id))
    : openTasks
  const visibleTask = isPreviewActive
    ? PREVIEW_TASKS.find(previewTask => previewTask.id === previewActiveTaskId) || PREVIEW_TASKS[0]
    : task

  useEffect(() => {
    if (!isPreviewActive) return

    if (previewOpenTaskIds.length === 0) {
      setPreviewMode(false)
      setPreviewOpenTaskIds(PREVIEW_TASKS.map(previewTask => previewTask.id))
      setPreviewActiveTaskId(PREVIEW_TASKS[0]?.id || '')
      return
    }

    if (!previewOpenTaskIds.includes(previewActiveTaskId)) {
      setPreviewActiveTaskId(previewOpenTaskIds[0] || PREVIEW_TASKS[0]?.id || '')
    }
  }, [isPreviewActive, previewActiveTaskId, previewOpenTaskIds])

  const handleSelectTask = (taskId: string) => {
    if (isPreviewActive) {
      setPreviewActiveTaskId(taskId)
      return
    }
    onSelectTask(taskId)
  }

  const handleCloseTask = (taskId: string) => {
    if (isPreviewActive) {
      const nextOpenTaskIds = previewOpenTaskIds.filter(id => id !== taskId)
      if (previewActiveTaskId === taskId) {
        const currentIndex = previewOpenTaskIds.indexOf(taskId)
        const fallbackTaskId =
          previewOpenTaskIds[currentIndex + 1] ||
          previewOpenTaskIds[currentIndex - 1] ||
          nextOpenTaskIds[0] ||
          PREVIEW_TASKS[0]?.id ||
          ''
        setPreviewActiveTaskId(fallbackTaskId)
      }
      setPreviewOpenTaskIds(nextOpenTaskIds)
      if (nextOpenTaskIds.length === 0) {
        setPreviewMode(false)
        setPreviewOpenTaskIds(PREVIEW_TASKS.map(previewTask => previewTask.id))
        setPreviewActiveTaskId(PREVIEW_TASKS[0]?.id || '')
      }
      return
    }

    onCloseTask(taskId)
  }

  const renderWorkspacePanel = (order: number) => (
    <ResizablePanel
      id="workspace"
      order={order}
      defaultSize={isVerticalSplit ? 58 : 62}
      minSize={isVerticalSplit ? 36 : 38}
      className="min-h-0 min-w-0"
    >
      <div className="flex h-full min-w-0 flex-col bg-[#111111]">
        {visibleTask ? (
          <SummaryContent key={visibleTask.id} task={visibleTask} />
        ) : (
          <EmptyWorkspace
            onNewTask={onNewTask}
            onPreviewDemo={ENABLE_WORKSPACE_MOCK ? () => setPreviewMode(true) : undefined}
          />
        )}
      </div>
    </ResizablePanel>
  )

  const renderMediaPanel = (order: number) => (
    <ResizablePanel
      id="media-chat"
      order={order}
      defaultSize={isVerticalSplit ? 42 : 38}
      minSize={isVerticalSplit ? 28 : 26}
      className="min-h-0 min-w-0"
    >
      <div className="h-full min-w-0 bg-[#141414]">
        <VideoChatPanel
          task={visibleTask || null}
          mode={mediaPanelMode}
          onModeChange={setMediaPanelMode}
          onSwapPanels={() => setPanelsSwapped(prev => !prev)}
        />
      </div>
    </ResizablePanel>
  )

  const resizeHandle = (
    <ResizableHandle
      withHandle
      className="hover:bg-primary/60 data-[resize-handle-state=drag]:bg-primary bg-neutral-800/90 transition-colors"
    />
  )

  return (
    <div className="absolute inset-0 flex flex-col bg-[#0E0E0E]">
      <WorkspaceTabs
        tasks={visibleTasks}
        activeTaskId={isPreviewActive ? previewActiveTaskId : activeTaskId}
        onSelectTask={handleSelectTask}
        onCloseTask={handleCloseTask}
        onNewTask={onNewTask}
      />
      <ResizablePanelGroup
        direction={splitDirection}
        autoSaveId="workspace-main-split"
        className="min-h-0 flex-1 bg-[#0E0E0E]"
      >
        {panelsSwapped ? (
          <>
            {renderMediaPanel(1)}
            {resizeHandle}
            {renderWorkspacePanel(2)}
          </>
        ) : (
          <>
            {renderWorkspacePanel(1)}
            {resizeHandle}
            {renderMediaPanel(2)}
          </>
        )}
      </ResizablePanelGroup>
    </div>
  )
}
