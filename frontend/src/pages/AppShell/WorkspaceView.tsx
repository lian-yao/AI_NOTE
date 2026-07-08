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
  Loader2, Trash2,
  MessageSquare,
  Maximize2,
  Minimize2,
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
import { resolveApiMediaUrl, resolveVideoPlayer, type VideoPlayerSource } from '@/services/video'
import {
  formatDate,
  formatTime,
  getLatestMarkdown,
  getTaskAuthor,
  getTaskCoverUrl,
  getTaskTimelineSections,
  getTaskTitle,
  resolveDisplayImageUrl,
} from './utils'
import MarkdownRenderer from './components/MarkdownRenderer'

const MarkmapEditor = lazy(() => import('./components/MarkmapComponent'))
const ChatPanel = lazy(() => import('./components/ChatPanel'))
type MediaPanelMode = 'video-chat' | 'chat-only'

interface VideoSeekRequest {
  id: number
  taskId: string
  time: number
}

interface TimelineMarker {
  key: string
  title: string
  content: string
  time: number
  endTime: number
  screenshotUrl: string
}

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
  const cancelTask = useTaskStore(state => state.cancelTask)
  const removeTask = useTaskStore(state => state.removeTask)

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
          {isFailed
            ? task.message || '请检查后端日志或稍后重试。'
            : '任务正在执行，完成后会自动刷新。'}
        </p>
        {!isFailed && (
          <button
            type="button"
            onClick={() => cancelTask(task.id)}
            className="mt-4 flex items-center gap-1.5 rounded-lg border border-neutral-700 bg-neutral-800/50 px-4 py-2 text-sm font-medium text-neutral-300 transition-colors hover:bg-neutral-700/50"
          >
            <X size={15} />
            取消任务
          </button>
        )}
      </div>
      {isFailed && (
        <div className="flex gap-3">
        <button
          type="button"
          onClick={() => retryTask(task.id)}
          className="flex items-center gap-1.5 rounded-lg border border-red-400/30 bg-red-500/10 px-4 py-2 text-sm font-medium text-red-200 transition-colors hover:bg-red-500/20"
        >
          <RefreshCcw size={15} />
          重试生成
        </button>
        <button
          type="button"
          onClick={() => removeTask(task.id)}
          className="flex items-center gap-1.5 rounded-lg border border-neutral-700 bg-neutral-800/50 px-4 py-2 text-sm font-medium text-neutral-300 transition-colors hover:bg-red-500/20 hover:text-red-300"
        >
          <Trash2 size={15} />
          删除记录
        </button>
        </div>
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

function DeepReadingScreenshot({ src, alt }: { src: string; alt: string }) {
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    setFailed(false)
  }, [src])

  if (!src || failed) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 px-4 text-center text-xs text-neutral-600">
        <Video size={22} strokeWidth={1.5} />
        <span>{src ? '截图暂不可用' : '关键截图待生成'}</span>
      </div>
    )
  }

  return (
    <img
      src={src}
      alt={alt}
      loading="lazy"
      referrerPolicy="no-referrer"
      onError={() => setFailed(true)}
      className="h-full w-full object-cover"
    />
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
      metrics.trackPadding + (viewport.scrollTop / metrics.maxScrollTop) * metrics.maxThumbTop

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

function SummaryContent({
  task,
  onSeekToTime,
}: {
  task: Task
  onSeekToTime: (seconds: number) => void
}) {
  const [activeTab, setActiveTab] = useState<'summary' | 'deep-reading' | 'transcript' | 'mindmap'>(
    'summary'
  )
  const [isEditing, setIsEditing] = useState(false)
  const [editorMode, setEditorMode] = useState<'write' | 'split' | 'preview'>('split')
  const [draftContent, setDraftContent] = useState('')
  const [showDeepReadingScreenshots, setShowDeepReadingScreenshots] = useState(true)
  const retryTask = useTaskStore(state => state.retryTask)
  const updateTaskContent = useTaskStore(state => state.updateTaskContent)
  const { content, version } = getLatestMarkdown(task.markdown)
  const segments = useMemo(() => task.transcript?.segments || [], [task.transcript?.segments])
  const timelineSections = useMemo(() => getTaskTimelineSections(task, content), [content, task])
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
          <MarkdownRenderer
            value={content}
            emptyPlaceholder="暂无总结内容"
            onSeekTimestamp={onSeekToTime}
          />
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
        <MarkdownRenderer
          value={draftContent}
          emptyPlaceholder="预览内容为空"
          onSeekTimestamp={onSeekToTime}
        />
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
              <span>章节 ({timelineSections.length})</span>
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
        <WorkspaceScrollArea active={activeTab === 'summary'} className="pt-2 pr-1 pb-8 pl-2">
          <div className="w-full max-w-none">{renderMarkdownEditor()}</div>
        </WorkspaceScrollArea>

        <WorkspaceScrollArea active={activeTab === 'deep-reading'} className="pt-6 pr-3 pb-20 pl-6">
          <div className="mx-auto max-w-5xl space-y-8">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-neutral-800/50 pb-4">
              <div>
                <h2 className="text-lg font-bold text-neutral-100">视频主题: {title}</h2>
                <p className="mt-2 text-xs text-neutral-500">
                  按内容时间块阅读字幕原文，左侧保留对应关键截图
                </p>
              </div>
              <div className="flex items-center gap-2 text-xs text-neutral-400">
                <span>显示截图</span>
                <button
                  type="button"
                  role="switch"
                  aria-checked={showDeepReadingScreenshots}
                  onClick={() => setShowDeepReadingScreenshots(value => !value)}
                  className={`relative h-5 w-9 rounded-full transition-colors ${
                    showDeepReadingScreenshots ? 'bg-neutral-100' : 'bg-neutral-700'
                  }`}
                >
                  <span
                    className={`absolute top-0.5 h-4 w-4 rounded-full bg-black transition-transform ${
                      showDeepReadingScreenshots ? 'translate-x-4' : 'translate-x-0.5'
                    }`}
                  />
                </button>
              </div>
            </div>
            {timelineSections.length > 0 ? (
              timelineSections.map(section => {
                const relatedSegments = segments.filter(segment => {
                  if (section.endTime <= section.startTime) {
                    return segment.start >= section.startTime
                  }
                  return segment.end >= section.startTime && segment.start <= section.endTime
                })
                const timeLabel =
                  section.endTime > section.startTime
                    ? `${formatTime(section.startTime)} - ${formatTime(section.endTime)}`
                    : formatTime(section.startTime)
                const screenshotUrl =
                  resolveTaskImageUrl(section.screenshotUrl, task.audioMeta?.platform) ||
                  getTaskSnapshotUrl(task, section.startTime)

                return (
                  <section
                    key={section.key}
                    className="grid gap-5 border-b border-neutral-800/45 pb-8 last:border-b-0 lg:grid-cols-[240px_minmax(0,1fr)]"
                  >
                    {showDeepReadingScreenshots && (
                      <div className="lg:pt-1">
                        <div className="aspect-video overflow-hidden rounded-md border border-neutral-800 bg-[#080808]">
                          <DeepReadingScreenshot
                            src={screenshotUrl}
                            alt={`${section.title} 关键截图`}
                          />
                        </div>
                      </div>
                    )}

                    <div className="min-w-0">
                      <div className="mb-4 flex flex-wrap items-center gap-3">
                        <button
                          type="button"
                          onClick={() => onSeekToTime(section.startTime)}
                          className="text-primary rounded border border-blue-400/25 bg-blue-500/10 px-2 py-0.5 font-mono text-xs transition-colors hover:border-blue-300/60 hover:bg-blue-500/20"
                          title="跳转到视频位置"
                        >
                          {timeLabel}
                        </button>
                        <h3 className="min-w-0 flex-1 text-xl font-bold text-neutral-100">
                          {section.title}
                        </h3>
                        <span className="shrink-0 text-xs text-neutral-600">
                          {relatedSegments.length} 条字幕
                        </span>
                      </div>

                      {relatedSegments.length > 0 ? (
                        <div className="space-y-2 text-[15px] leading-7 text-neutral-100">
                          {relatedSegments.map(segment => (
                            <button
                              key={`${segment.start}-${segment.text}`}
                              type="button"
                              onClick={() => onSeekToTime(segment.start)}
                              className="block w-full rounded-md px-2 py-0.5 text-left transition-colors hover:bg-blue-500/10"
                              title={`跳转到 ${formatTime(segment.start)}`}
                            >
                              {segment.text}
                            </button>
                          ))}
                        </div>
                      ) : (
                        <div className="rounded-md border border-dashed border-neutral-800 bg-[#0A0A0A] px-4 py-8 text-center text-sm text-neutral-600">
                          当前时间范围内暂无字幕原文
                        </div>
                      )}
                    </div>
                  </section>
                )
              })
            ) : (
              <div className="flex h-32 items-center justify-center rounded-xl border border-dashed border-neutral-800 bg-[#1A1A1A] text-sm text-neutral-600">
                当前笔记还没有可用的 AI 时间分块，重新总结后会根据内容整理生成。
              </div>
            )}
          </div>
        </WorkspaceScrollArea>

        <WorkspaceScrollArea active={activeTab === 'transcript'} className="pt-6 pr-3 pb-20 pl-6">
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
                    <button
                      type="button"
                      onClick={() => onSeekToTime(segment.start)}
                      className="text-primary w-14 shrink-0 text-left font-mono transition-colors hover:text-blue-200"
                      title="跳转到视频位置"
                    >
                      {formatTime(segment.start)}
                    </button>
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

function resolveTaskImageUrl(rawUrl: string, platform = ''): string {
  const displayUrl = resolveDisplayImageUrl(rawUrl, platform)
  if (!displayUrl) return ''
  if (/^\/(?:api|static)\//i.test(displayUrl)) {
    return resolveApiMediaUrl(displayUrl)
  }
  return displayUrl
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

function getTaskSnapshotUrl(task: Task | null, seconds: number | undefined): string {
  const videoId = getTaskVideoId(task)
  if (!videoId) return ''

  const safeSeconds = Math.max(0, Math.floor(Number.isFinite(seconds) ? Number(seconds) : 0))
  return resolveApiMediaUrl(
    `/api/v1/videos/${encodeURIComponent(videoId)}/snapshot?time=${safeSeconds}`
  )
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

function isLocalSource(value: string): boolean {
  return value.startsWith('local://')
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

function getTimedEmbedUrl(value: string, seconds: number, autoplay = true): string {
  const safeSeconds = Math.max(0, Math.floor(Number.isFinite(seconds) ? seconds : 0))

  try {
    const base =
      typeof window === 'undefined' ? 'https://player.bilibili.com/' : window.location.href
    const url = new URL(value, base)
    url.searchParams.set('t', String(safeSeconds))
    if (autoplay) url.searchParams.set('autoplay', '1')
    return url.toString()
  } catch {
    const separator = value.includes('?') ? '&' : '?'
    const autoplayParam = autoplay ? '&autoplay=1' : ''
    return `${value}${separator}t=${safeSeconds}${autoplayParam}`
  }
}

function TaskVideoPlayer({
  task,
  title,
  coverUrl,
  seekRequest,
}: {
  task: Task
  title: string
  coverUrl: string
  seekRequest?: VideoSeekRequest | null
}) {
  const playerHostRef = useRef<HTMLDivElement>(null)
  const videoRef = useRef<HTMLVideoElement>(null)
  const pendingSeekRef = useRef<number | null>(null)
  const timelineTrackRef = useRef<HTMLDivElement>(null)
  const subtitleDragRef = useRef<{ pointerId: number } | null>(null)
  const [playerSource, setPlayerSource] = useState<VideoPlayerSource | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [playerMode, setPlayerMode] = useState<'native' | 'embed'>('native')
  const [playing, setPlaying] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(0)
  const [playbackRate, setPlaybackRate] = useState(1)
  const [subtitlesVisible, setSubtitlesVisible] = useState(true)
  const [subtitlePosition, setSubtitlePosition] = useState({ x: 50, y: 76 })
  const [subtitleDragging, setSubtitleDragging] = useState(false)
  const [controlsVisible, setControlsVisible] = useState(true)
  const [controlInteractionKey, setControlInteractionKey] = useState(0)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [reloadKey, setReloadKey] = useState(0)
  const [hoveredTimelineMarker, setHoveredTimelineMarker] = useState<
    (TimelineMarker & { left: number }) | null
  >(null)
  const [embedSeekRequest, setEmbedSeekRequest] = useState<{
    id: number
    time: number
    autoplay: boolean
  } | null>(null)
  const sourceUrl = getTaskSourceUrl(task)
  const videoId = getTaskVideoId(task)
  const fallbackEmbedUrl = getTaskEmbedUrl(task)
  const embedUrl = playerSource?.embed_url || fallbackEmbedUrl
  const iframeSrc = useMemo(
    () =>
      embedSeekRequest && embedUrl
        ? getTimedEmbedUrl(embedUrl, embedSeekRequest.time, embedSeekRequest.autoplay)
        : embedUrl,
    [embedSeekRequest, embedUrl]
  )
  const posterUrl = playerSource?.cover_url || coverUrl
  const streamUrl = playerSource?.local_stream_url || playerSource?.stream_url || ''
  const quality = task.formData?.quality || '1080p'
  const segments = useMemo(() => task.transcript?.segments || [], [task.transcript?.segments])
  const knownDuration = duration || playerSource?.duration_seconds || task.audioMeta?.duration || 0
  const markdownContent = useMemo(() => getLatestMarkdown(task.markdown).content, [task.markdown])
  const activeSegment = useMemo(() => {
    return (
      segments.find(segment => currentTime >= segment.start && currentTime < segment.end) || null
    )
  }, [currentTime, segments])
  const timelineMarkers = useMemo<TimelineMarker[]>(() => {
    return getTaskTimelineSections(task, markdownContent).map((section, index) => ({
      key: section.key || `section-${index}`,
      title: section.title,
      content: section.content,
      time: section.startTime,
      endTime: section.endTime,
      screenshotUrl:
        resolveTaskImageUrl(section.screenshotUrl, task.audioMeta?.platform) ||
        getTaskSnapshotUrl(task, section.startTime),
    }))
  }, [markdownContent, task])
  const timelineDuration = useMemo(() => {
    const lastMarkerTime = timelineMarkers.reduce(
      (max, marker) => Math.max(max, marker.endTime || marker.time),
      0
    )
    return Math.max(knownDuration, lastMarkerTime, currentTime, 1)
  }, [currentTime, knownDuration, timelineMarkers])

  const handleTimelinePointerMove = useCallback(
    (event: ReactPointerEvent<HTMLDivElement>) => {
      if (timelineMarkers.length === 0) {
        setHoveredTimelineMarker(null)
        return
      }

      const rect = event.currentTarget.getBoundingClientRect()
      if (rect.width <= 0) return

      const left = Math.min(100, Math.max(0, ((event.clientX - rect.left) / rect.width) * 100))
      const hoveredTime = (left / 100) * timelineDuration
      const hoverGraceSeconds = Math.max(4, timelineDuration * 0.008)
      let nextMarker: TimelineMarker | null = null
      let nextDistance = Number.POSITIVE_INFINITY

      for (const marker of timelineMarkers) {
        const start = marker.time
        const end = Math.max(marker.endTime || marker.time, marker.time)
        const distance =
          hoveredTime < start ? start - hoveredTime : hoveredTime > end ? hoveredTime - end : 0

        if (distance < nextDistance) {
          nextMarker = marker
          nextDistance = distance
        }
      }

      if (!nextMarker || nextDistance > hoverGraceSeconds) {
        setHoveredTimelineMarker(null)
        return
      }

      setHoveredTimelineMarker(previous => {
        if (previous?.key === nextMarker?.key && Math.abs(previous.left - left) < 0.25) {
          return previous
        }
        return {
          ...nextMarker,
          left,
        }
      })
    },
    [timelineDuration, timelineMarkers]
  )

  const showControls = useCallback(() => {
    setControlsVisible(true)
    setControlInteractionKey(value => value + 1)
  }, [])

  const updateSubtitlePosition = useCallback((clientX: number, clientY: number) => {
    const host = playerHostRef.current
    if (!host) return

    const rect = host.getBoundingClientRect()
    if (rect.width <= 0 || rect.height <= 0) return

    const x = Math.min(90, Math.max(10, ((clientX - rect.left) / rect.width) * 100))
    const y = Math.min(84, Math.max(16, ((clientY - rect.top) / rect.height) * 100))
    setSubtitlePosition({ x, y })
  }, [])

  const handleSubtitlePointerDown = useCallback(
    (event: ReactPointerEvent<HTMLDivElement>) => {
      event.preventDefault()
      event.stopPropagation()
      subtitleDragRef.current = { pointerId: event.pointerId }
      event.currentTarget.setPointerCapture(event.pointerId)
      setSubtitleDragging(true)
      showControls()
      updateSubtitlePosition(event.clientX, event.clientY)
    },
    [showControls, updateSubtitlePosition]
  )

  const handleSubtitlePointerMove = useCallback(
    (event: ReactPointerEvent<HTMLDivElement>) => {
      if (subtitleDragRef.current?.pointerId !== event.pointerId) return
      event.preventDefault()
      event.stopPropagation()
      updateSubtitlePosition(event.clientX, event.clientY)
    },
    [updateSubtitlePosition]
  )

  const handleSubtitlePointerEnd = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    if (subtitleDragRef.current?.pointerId !== event.pointerId) return
    event.preventDefault()
    event.stopPropagation()
    subtitleDragRef.current = null
    setSubtitleDragging(false)
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId)
    }
  }, [])

  useEffect(() => {
    let cancelled = false

    setPlayerSource(null)
    setError('')
    setPlayerMode('native')
    setCurrentTime(0)
    setDuration(0)
    setPlaying(false)
    setEmbedSeekRequest(null)

    if (!sourceUrl) {
      setError('当前笔记缺少视频链接')
      return
    }

    const isLocal = isLocalSource(sourceUrl)
    if (!isBilibiliSource(sourceUrl) && !isLocal) {
      setError('当前内置播放器暂只支持 Bilibili 链接')
      return
    }

    setLoading(true)
    resolveVideoPlayer(sourceUrl, quality, videoId, { silent: true })
      .then(data => {
        if (cancelled) return
        setPlayerSource(data)
        const hasNativeSource = Boolean(data.local_stream_url || data.stream_url)
        setPlayerMode(currentMode =>
          isLocal
            ? 'native'
            : currentMode === 'embed' && (data.embed_url || fallbackEmbedUrl)
              ? 'embed'
              : hasNativeSource
                ? 'native'
                : 'embed'
        )
        if (!hasNativeSource && !(data.embed_url || fallbackEmbedUrl)) {
          setError(isLocal ? '本地视频文件尚未就绪，请等待处理完成' : '暂无可播放视频源')
        }
      })
      .catch(err => {
        if (cancelled) return
        setError(playerErrorMessage(err))
        setPlayerMode(!isPlayerAuthError(err) && fallbackEmbedUrl && !isLocal ? 'embed' : 'native')
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

  useEffect(() => {
    if (!playing || subtitleDragging) {
      setControlsVisible(true)
      return
    }

    const timer = window.setTimeout(() => {
      setControlsVisible(false)
    }, 2200)

    return () => window.clearTimeout(timer)
  }, [playing, subtitleDragging, controlInteractionKey])

  useEffect(() => {
    const syncFullscreenState = () => {
      setIsFullscreen(document.fullscreenElement === playerHostRef.current)
    }

    syncFullscreenState()
    document.addEventListener('fullscreenchange', syncFullscreenState)
    return () => document.removeEventListener('fullscreenchange', syncFullscreenState)
  }, [])

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

  const seekEmbedTo = useCallback((value: number, autoplay = true) => {
    const safeValue = Math.max(0, Number.isFinite(value) ? value : 0)
    setEmbedSeekRequest(prev => ({
      id: (prev?.id || 0) + 1,
      time: safeValue,
      autoplay,
    }))
    setCurrentTime(safeValue)
    return true
  }, [])

  const seekTo = useCallback(
    (value: number, autoplay = false) => {
      const safeValue = Math.max(0, Number.isFinite(value) ? value : 0)
      if (playerMode === 'embed' && embedUrl) {
        return seekEmbedTo(safeValue, autoplay)
      }

      const video = videoRef.current
      if (!video) {
        if (!streamUrl && embedUrl) {
          setPlayerMode('embed')
          return seekEmbedTo(safeValue, autoplay)
        }

        pendingSeekRef.current = safeValue
        return false
      }
      video.currentTime = safeValue
      setCurrentTime(safeValue)
      if (autoplay) {
        void video.play().catch(() => {})
      }
      return true
    },
    [embedUrl, playerMode, seekEmbedTo, streamUrl]
  )

  const toggleFullscreen = () => {
    const host = playerHostRef.current
    if (!host) return

    if (document.fullscreenElement === host) {
      void document.exitFullscreen?.()
      return
    }

    if (host.requestFullscreen) {
      void host.requestFullscreen()
    }
  }

  const sourceIsLocal = isLocalSource(sourceUrl)
  const canUseNative = Boolean(streamUrl)
  const canUseEmbed = Boolean(embedUrl) && !sourceIsLocal
  const canShowEmbed = playerMode === 'embed' && canUseEmbed
  const canShowVideo = playerMode === 'native' && canUseNative

  useEffect(() => {
    if (!seekRequest) return
    if (seekRequest.taskId !== task.id) return

    const jumped = seekTo(seekRequest.time, true)
    if (!jumped && !streamUrl && !embedUrl && !loading) {
      toast.error('当前播放器源暂不支持从笔记时间戳直接跳转')
    }
  }, [embedUrl, loading, seekRequest, seekTo, streamUrl, task.id])

  useEffect(() => {
    if (!canShowVideo || pendingSeekRef.current == null) return

    const target = pendingSeekRef.current
    const timer = window.setTimeout(() => {
      if (seekTo(target, true)) {
        pendingSeekRef.current = null
      }
    }, 0)

    return () => window.clearTimeout(timer)
  }, [canShowVideo, seekRequest?.id, seekTo, streamUrl])

  return (
    <div
      ref={playerHostRef}
      onPointerMove={showControls}
      onPointerLeave={() => {
        if (playing && !subtitleDragging) setControlsVisible(false)
      }}
      onFocusCapture={showControls}
      className="workspace-video-player relative aspect-video shrink-0 overflow-hidden border-b border-neutral-800 bg-black"
    >
      <div
        className={`absolute top-3 right-3 z-30 rounded-full border border-white/10 bg-black/38 p-1 text-xs text-neutral-200 shadow-2xl backdrop-blur-md transition-all duration-300 ${
          controlsVisible || !playing
            ? 'translate-y-0 opacity-100'
            : 'pointer-events-none -translate-y-2 opacity-0'
        }`}
      >
        <div className="relative grid w-[138px] grid-cols-2">
          <span
            aria-hidden
            className="absolute top-0 bottom-0 left-0 w-1/2 rounded-full bg-white shadow-[0_5px_18px_rgba(255,255,255,0.18)] transition-transform duration-300 ease-out"
            style={{
              transform: playerMode === 'embed' ? 'translateX(100%)' : 'translateX(0)',
            }}
          />
        <button
          type="button"
          onClick={() => setPlayerMode('native')}
          disabled={!canUseNative}
          aria-pressed={playerMode === 'native'}
          className={`relative z-10 flex h-7 items-center justify-center gap-1 rounded-full px-2 transition-colors duration-300 disabled:cursor-not-allowed disabled:opacity-35 ${
            playerMode === 'native'
              ? 'text-neutral-950'
              : 'text-neutral-300 hover:text-white'
          }`}
          title="使用本地播放器"
        >
          <Video size={13} />
          <span>本地</span>
        </button>
        {!sourceIsLocal && (
        <button
          type="button"
          onClick={() => setPlayerMode('embed')}
          disabled={!canUseEmbed}
          aria-pressed={playerMode === 'embed'}
          className={`relative z-10 flex h-7 items-center justify-center gap-1 rounded-full px-2 transition-colors duration-300 disabled:cursor-not-allowed disabled:opacity-35 ${
            playerMode === 'embed'
              ? 'text-neutral-950'
              : 'text-neutral-300 hover:text-white'
          }`}
          title="使用 B 站播放器"
        >
          <ExternalLink size={13} />
          <span>B站</span>
        </button>
        )}
        </div>
      </div>

      {canShowEmbed ? (
        <iframe
          key={`${iframeSrc}-${embedSeekRequest?.id || 0}`}
          src={iframeSrc}
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
              className="absolute top-1/2 left-1/2 z-10 flex h-16 w-16 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full bg-black/55 text-white backdrop-blur-sm transition-colors hover:bg-black/75"
              aria-label="播放"
            >
              <Play size={30} fill="currentColor" />
            </button>
          )}

          {subtitlesVisible && activeSegment && (
            <div
              onPointerDown={handleSubtitlePointerDown}
              onPointerMove={handleSubtitlePointerMove}
              onPointerUp={handleSubtitlePointerEnd}
              onPointerCancel={handleSubtitlePointerEnd}
              className={`absolute z-20 max-w-[min(86%,760px)] select-none rounded-lg border px-3 py-2 text-center text-sm leading-relaxed text-white shadow-2xl backdrop-blur-sm transition-[border-color,background-color,box-shadow] ${
                subtitleDragging
                  ? 'cursor-grabbing border-sky-300/70 bg-black/82 shadow-sky-500/20'
                  : 'cursor-grab border-white/10 bg-black/68 hover:border-white/24'
              }`}
              style={{
                left: `${subtitlePosition.x}%`,
                top: `${subtitlePosition.y}%`,
                transform: 'translate(-50%, -50%)',
              }}
              title="拖动字幕位置"
            >
              {activeSegment.text}
            </div>
          )}

          <div
            className={`absolute inset-x-0 bottom-0 z-30 bg-gradient-to-t from-black/90 via-black/65 to-transparent px-3 pt-14 pb-3 transition-all duration-300 ${
              controlsVisible || !playing || subtitleDragging
                ? 'translate-y-0 opacity-100'
                : 'pointer-events-none translate-y-4 opacity-0'
            }`}
          >
            <div
              ref={timelineTrackRef}
              onPointerMove={handleTimelinePointerMove}
              onPointerLeave={() => setHoveredTimelineMarker(null)}
              className="relative mb-2 h-8"
            >
              <div className="pointer-events-none absolute top-[14px] right-0 left-0 h-[3px] -translate-y-1/2 rounded-sm bg-white/16" />
              {timelineMarkers.length > 0 &&
                timelineMarkers.map(marker => {
                  const left = Math.min(100, Math.max(0, (marker.time / timelineDuration) * 100))
                  const right = Math.min(
                    100,
                    Math.max(left, ((marker.endTime || marker.time) / timelineDuration) * 100)
                  )
                  const width = Math.max(0.35, right - left)
                  const isHovered = hoveredTimelineMarker?.key === marker.key
                  return (
                    <div
                      key={marker.key}
                      className={`pointer-events-none absolute top-[14px] z-0 h-[3px] -translate-y-1/2 rounded-sm transition-colors ${
                        isHovered ? 'bg-white/55' : 'bg-white/28'
                      }`}
                      style={{
                        left: `calc(${left}% + 2px)`,
                        width: `max(2px, calc(${width}% - 4px))`,
                      }}
                      aria-hidden
                    />
                  )
                })}
              <div
                className="pointer-events-none absolute top-[14px] left-0 z-10 h-[3px] -translate-y-1/2 rounded-sm bg-sky-400"
                style={{
                  width: `${Math.min(100, Math.max(0, (currentTime / timelineDuration) * 100))}%`,
                }}
              />
              {hoveredTimelineMarker && (
                <>
                  <div
                    className="pointer-events-none absolute top-[20px] z-30 h-0 w-0 -translate-x-1/2 border-x-[5px] border-t-[6px] border-x-transparent border-t-sky-300"
                    style={{ left: `${hoveredTimelineMarker.left}%` }}
                    aria-hidden
                  />
                  <div
                    className="pointer-events-none absolute bottom-10 z-40 w-52 overflow-hidden rounded-md border border-black/70 bg-[#101010]/98 text-left shadow-2xl backdrop-blur"
                    style={{
                      left: `${hoveredTimelineMarker.left}%`,
                      transform:
                        hoveredTimelineMarker.left < 12
                          ? 'translateX(0)'
                          : hoveredTimelineMarker.left > 88
                            ? 'translateX(-100%)'
                            : 'translateX(-50%)',
                    }}
                  >
                    <div className="relative aspect-video bg-black">
                      <DeepReadingScreenshot
                        src={hoveredTimelineMarker.screenshotUrl}
                        alt={`${hoveredTimelineMarker.title} 预览截图`}
                      />
                      <div className="absolute right-1.5 bottom-1.5 rounded bg-black/78 px-1.5 py-0.5 font-mono text-[11px] text-white">
                        {formatPlayerTime(hoveredTimelineMarker.time)}
                        {hoveredTimelineMarker.endTime > hoveredTimelineMarker.time
                          ? ` - ${formatPlayerTime(hoveredTimelineMarker.endTime)}`
                          : ''}
                      </div>
                    </div>
                    <div className="space-y-1 px-2.5 py-2">
                      <div className="line-clamp-1 text-xs font-semibold text-neutral-100">
                        {hoveredTimelineMarker.title}
                      </div>
                      {hoveredTimelineMarker.content && (
                        <div className="line-clamp-2 text-[11px] leading-4 text-neutral-400">
                          {hoveredTimelineMarker.content}
                        </div>
                      )}
                    </div>
                  </div>
                </>
              )}
              <input
                type="range"
                min={0}
                max={timelineDuration}
                step={0.1}
                value={currentTime}
                onChange={event => seekTo(Number(event.target.value))}
                className="workspace-timeline-range absolute inset-x-0 top-[14px] z-30 h-7 -translate-y-1/2 cursor-pointer bg-transparent"
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
                {playing ? (
                  <Pause size={16} fill="currentColor" />
                ) : (
                  <Play size={16} fill="currentColor" />
                )}
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
                      playbackRate === rate
                        ? 'bg-white text-black'
                        : 'bg-white/10 hover:bg-white/20'
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
                  onClick={toggleFullscreen}
                  className="flex h-7 w-7 items-center justify-center rounded-md bg-white/10 transition-colors hover:bg-white/20"
                  title={isFullscreen ? '退出全屏' : '全屏'}
                  aria-label={isFullscreen ? '退出全屏' : '全屏'}
                >
                  {isFullscreen ? <Minimize2 size={15} /> : <Maximize2 size={15} />}
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
        <div className="absolute top-14 left-3 z-30 flex items-center gap-2 rounded-full bg-black/70 px-2.5 py-1 text-xs text-neutral-100 backdrop-blur-sm">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          解析中
        </div>
      )}

      {sourceUrl && (
        <a
          href={sourceUrl}
          target="_blank"
          rel="noreferrer"
          className="absolute top-3 left-3 z-30 flex h-8 w-8 items-center justify-center rounded-full bg-black/70 text-neutral-200 backdrop-blur-sm transition-colors hover:bg-neutral-800 hover:text-white"
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
  seekRequest,
}: {
  task: Task | null
  mode: MediaPanelMode
  onModeChange: (mode: MediaPanelMode) => void
  onSwapPanels: () => void
  seekRequest?: VideoSeekRequest | null
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
          <TaskVideoPlayer
            task={task}
            title={title}
            coverUrl={coverUrl}
            seekRequest={seekRequest}
          />

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
  const [videoSeekRequest, setVideoSeekRequest] = useState<VideoSeekRequest | null>(null)
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

  const handleSeekToTime = useCallback(
    (seconds: number) => {
      if (!Number.isFinite(seconds) || !visibleTask) return
      setMediaPanelMode('video-chat')
      setVideoSeekRequest(prev => ({
        id: (prev?.id || 0) + 1,
        taskId: visibleTask.id,
        time: Math.max(0, seconds),
      }))
    },
    [visibleTask]
  )

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
          <SummaryContent key={visibleTask.id} task={visibleTask} onSeekToTime={handleSeekToTime} />
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
          seekRequest={videoSeekRequest}
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
