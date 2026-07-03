import { lazy, Suspense, useEffect, useMemo, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { toast } from 'react-hot-toast'
import {
  Bot,
  CheckCircle2,
  Copy,
  Download,
  Eye,
  FileText,
  Loader2,
  Maximize,
  MessageSquare,
  PenSquare,
  Play,
  Plus,
  RefreshCcw,
  Share,
  Subtitles,
  Video,
  Volume2,
  X,
} from 'lucide-react'
import type { Task } from '@/store/taskStore'
import { useTaskStore } from '@/store/taskStore'
import { getTaskLogs, type TaskLogItem } from '@/services/task'
import {
  formatDate,
  formatTime,
  getLatestMarkdown,
  getTaskAuthor,
  getTaskCoverUrl,
  getTaskTitle,
  groupSegments,
} from './utils'

const MarkmapEditor = lazy(() => import('./components/MarkmapComponent'))
const ChatPanel = lazy(() => import('./components/ChatPanel'))

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
  status: Task['status'] = 'SUCCESS',
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
      raw_info: { uploader: '示例作者' },
      title,
      video_id: id,
    },
    createdAt,
    formData: {
      video_url: `preview://${id}`,
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
    ['这是第一段示例字幕。', '它用于确认标签切换效果。', '关闭后会回退到相邻标签。'],
  ),
  createPreviewTask(
    'preview-note-b',
    '示例笔记 B',
    `# 第二个示例

这条示例笔记用来演示多个标签同时存在时的切换效果。

> 前端开发阶段，这比等后端数据更直观。
`,
    ['第二条示例字幕。', '它会作为另一个标签存在。'],
    'RUNNING',
  ),
  createPreviewTask(
    'preview-note-c',
    '失败任务预览',
    `# 失败态预览

这条 mock 用来确认标签栏里的失败状态、关闭回退和右侧信息栏。
`,
    ['第三条示例字幕。', '这里模拟任务失败时仍保留在工作区标签。'],
    'FAILED',
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
                className={`group flex h-9 min-w-[150px] max-w-[240px] shrink-0 items-center rounded-t-lg border px-2 transition-colors ${
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
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      )}
      <div>
        <p className={`text-lg font-bold ${isFailed ? 'text-red-400' : 'text-neutral-200'}`}>
          {label}
        </p>
        <p className="mt-2 text-sm text-neutral-500">
          {isFailed ? '请检查后端日志或稍后重试。' : '任务正在执行，完成后会自动刷新。'}
        </p>
      </div>
      {logs.length > 0 && (
        <div className="w-full max-w-xl rounded-xl border border-neutral-800 bg-[#161616] p-4 text-left">
          <div className="mb-3 text-xs font-medium text-neutral-500">后端任务日志</div>
          <div className="space-y-2">
            {logs.map((log, index) => (
              <div key={log.id || `${log.created_at}-${index}`} className="text-xs text-neutral-400">
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
          <div className="absolute left-1/2 top-1/2 h-10 w-40 -translate-x-1/2 -translate-y-1/2 animate-pulse rounded-full bg-primary/20" />
          <div className="absolute left-[18%] top-[22%] h-7 w-28 animate-pulse rounded-full bg-neutral-800" />
          <div className="absolute right-[16%] top-[28%] h-7 w-32 animate-pulse rounded-full bg-neutral-800" />
          <div className="absolute bottom-[24%] left-[24%] h-7 w-36 animate-pulse rounded-full bg-neutral-800" />
          <div className="absolute bottom-[18%] right-[24%] h-7 w-24 animate-pulse rounded-full bg-neutral-800" />
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
        <div className="ml-12 space-y-2 rounded-xl bg-primary/10 p-3">
          <div className="h-3 w-32 animate-pulse rounded bg-primary/30" />
          <div className="h-3 w-4/5 animate-pulse rounded bg-primary/20" />
        </div>
      </div>
      <div className="border-t border-neutral-800 p-4">
        <div className="h-10 animate-pulse rounded-xl bg-neutral-800" />
      </div>
    </div>
  )
}

function SummaryContent({ task }: { task: Task }) {
  const [activeTab, setActiveTab] = useState<'summary' | 'deep-reading' | 'transcript' | 'mindmap'>(
    'summary',
  )
  const [expandedGroups, setExpandedGroups] = useState<Record<number, boolean>>({})
  const retryTask = useTaskStore(state => state.retryTask)
  const { content, version } = getLatestMarkdown(task.markdown)
  const segments = useMemo(() => task.transcript?.segments || [], [task.transcript?.segments])
  const segmentGroups = useMemo(() => groupSegments(segments, 8), [segments])
  const title = getTaskTitle(task)
  const isPreviewTask = task.formData.provider_id === 'preview'

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(
        activeTab === 'transcript'
          ? segments.map(segment => `[${formatTime(segment.start)}] ${segment.text}`).join('\n')
          : content,
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
        : content
    const blob = new Blob([body], { type: 'text/markdown;charset=utf-8' })
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = `${title || 'note'}${activeTab === 'transcript' ? '-transcript' : ''}.md`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(link.href)
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
                  ? 'border-b-2 border-primary text-primary'
                  : 'text-neutral-400 hover:text-neutral-200'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="flex h-12 shrink-0 items-center justify-between border-b border-neutral-800/50 bg-[#161616] px-6">
        <div className="flex items-center gap-4 text-sm text-neutral-400">
          <span>章节 ({segmentGroups.length})</span>
          {version && <span className="text-xs">版本 {version.ver_id.slice(-6)}</span>}
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

      <div className="flex shrink-0 items-center justify-between px-6 py-3">
        <div className="flex items-center gap-2 text-sm text-primary">
          <CheckCircle2 size={16} />
          <span>{statusLabel[task.status]}</span>
        </div>
        <div className="flex items-center gap-4">
          <button
            type="button"
            onClick={() => toast('编辑模式稍后接入。')}
            className="flex items-center gap-1.5 text-xs text-neutral-400 transition-colors hover:text-neutral-200"
          >
            <PenSquare size={14} />
            编辑
          </button>
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

      <div className="relative flex-1 overflow-hidden">
        <div
          className={`custom-scrollbar absolute inset-0 overflow-y-auto px-6 pb-20 pt-6 ${
            activeTab === 'summary' ? 'block' : 'hidden'
          }`}
        >
          <div className="mx-auto max-w-3xl">
            <h2 className="mb-4 text-2xl font-bold text-neutral-100">{title}</h2>
            {content ? (
              <div className="prose prose-invert max-w-none prose-headings:text-neutral-100 prose-a:text-primary prose-strong:text-neutral-100 prose-code:text-neutral-100 prose-pre:bg-[#0A0A0A]">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
              </div>
            ) : (
              <div className="flex h-32 items-center justify-center rounded-xl border border-dashed border-neutral-800 bg-[#1A1A1A] text-sm text-neutral-600">
                暂无总结内容
              </div>
            )}
          </div>
        </div>

        <div
          className={`custom-scrollbar absolute inset-0 overflow-y-auto px-6 pb-20 pt-6 ${
            activeTab === 'deep-reading' ? 'block' : 'hidden'
          }`}
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
                      <span className="font-mono text-primary">{formatTime(group.start)}</span>
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
                          <div key={`${segment.start}-${segment.text}`} className="flex gap-4 text-sm">
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
        </div>

        <div
          className={`custom-scrollbar absolute inset-0 overflow-y-auto px-6 pb-20 pt-6 ${
            activeTab === 'transcript' ? 'block' : 'hidden'
          }`}
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
                    <div className="w-14 shrink-0 font-mono text-primary">
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
        </div>

        <div className={`absolute inset-0 ${activeTab === 'mindmap' ? 'block' : 'hidden'}`}>
          {activeTab !== 'mindmap' ? null : content ? (
            <Suspense fallback={<MindmapFallback />}>
              <MarkmapEditor value={content} onChange={() => {}} height="100%" title={title} />
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

function VideoChatPanel({ task }: { task: Task | null }) {
  const [chatReadyToLoad, setChatReadyToLoad] = useState(false)
  const coverUrl = getTaskCoverUrl(task)
  const title = getTaskTitle(task)
  const author = getTaskAuthor(task)
  const createdAt = formatDate(task?.createdAt)
  const duration = formatTime(task?.audioMeta?.duration)
  const taskId = task?.id
  const taskStatus = task?.status
  const isPreviewTask = task?.formData.provider_id === 'preview'

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
      <div className="flex h-full flex-col items-center justify-center border-l border-neutral-800 bg-[#111111]">
        <div className="mb-4 text-neutral-700">
          <Video size={48} strokeWidth={1} />
        </div>
        <p className="text-sm text-neutral-500">等待视频载入...</p>
      </div>
    )
  }

  if (isPreviewTask) {
    return (
      <div className="flex h-full flex-col border-l border-neutral-800 bg-[#111111]">
        <div className="relative aspect-video shrink-0 overflow-hidden border-b border-neutral-800 bg-black">
          <div className="absolute inset-0 flex items-center justify-center bg-neutral-900">
            <div className="flex flex-col items-center text-neutral-600">
              <Video size={32} className="mb-2 opacity-30" />
              <span className="text-xs">预览模式</span>
            </div>
          </div>
          <div className="absolute left-3 top-3 rounded-full bg-black/70 px-2 py-1 text-xs text-neutral-200 backdrop-blur-sm">
            示例数据
          </div>
        </div>

        <div className="shrink-0 border-b border-neutral-800 p-4">
          <div className="mb-2 flex items-center justify-between gap-4">
            <h3 className="line-clamp-1 text-lg font-bold text-neutral-100">{title}</h3>
            <span className="shrink-0 rounded bg-primary/10 px-2 py-1 text-xs text-primary">
              预览
            </span>
          </div>
          <div className="flex items-center gap-3">
            {author && <span className="text-sm font-medium text-primary">{author}</span>}
            {createdAt && <span className="text-xs text-neutral-500">{createdAt}</span>}
          </div>
        </div>

        <div className="flex min-h-0 flex-1 items-center justify-center bg-[#161616] px-6 text-center text-sm text-neutral-400">
          这里保留的是演示位，你切换左侧标签时可以看到多个打开记录、关闭回退和空态重现。
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col border-l border-neutral-800 bg-[#111111]">
      <div className="relative aspect-video shrink-0 overflow-hidden border-b border-neutral-800 bg-black">
        <div className="absolute inset-0 flex items-center justify-center bg-neutral-900">
          {coverUrl ? (
            <img
              src={coverUrl}
              alt={title}
              referrerPolicy="no-referrer"
              className="h-full w-full object-cover opacity-70"
            />
          ) : (
            <div className="flex flex-col items-center text-neutral-600">
              <Video size={32} className="mb-2 opacity-30" />
              <span className="text-xs">暂无画面</span>
            </div>
          )}
        </div>
        <div className="absolute bottom-0 left-0 right-0 flex h-12 items-center justify-between bg-gradient-to-t from-black/80 to-transparent px-4">
          <div className="flex items-center gap-4 text-white">
            <Play size={18} fill="currentColor" />
            <div className="flex items-center gap-2 text-xs font-medium">
              <span>00:00</span>
              <span>/</span>
              <span>{duration}</span>
            </div>
          </div>
          <div className="flex items-center gap-4 text-white">
            <Volume2 size={18} />
            <Maximize size={18} />
          </div>
        </div>
      </div>

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
          {author && <span className="text-sm font-medium text-primary">{author}</span>}
          {createdAt && <span className="text-xs text-neutral-500">{createdAt}</span>}
        </div>
      </div>

      <div className="flex min-h-0 flex-1 flex-col overflow-hidden bg-[#161616]">
        <div className="flex h-10 shrink-0 items-center justify-between border-b border-neutral-800 bg-[#1A1A1A] px-4">
          <span className="flex items-center gap-2 text-sm font-medium text-neutral-300">
            <MessageSquare size={14} />
            视频问答
          </span>
        </div>
        {task.status === 'SUCCESS' ? (
          chatReadyToLoad ? (
            <Suspense fallback={<ChatPanelFallback />}>
              <ChatPanel taskId={task.id} mode="half" onModeChange={() => {}} />
            </Suspense>
          ) : (
            <ChatPanelFallback />
          )
        ) : (
          <div className="flex flex-1 items-center justify-center px-6 text-center text-sm text-neutral-500">
            <div>
              <Bot className="mx-auto mb-3 h-6 w-6 text-neutral-600" />
              笔记完成后即可基于视频内容提问。
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
    PREVIEW_TASKS.map(previewTask => previewTask.id),
  )
  const [previewActiveTaskId, setPreviewActiveTaskId] = useState(PREVIEW_TASKS[0]?.id || '')
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

  return (
    <div className="absolute inset-0 flex flex-col bg-[#0E0E0E]">
      <WorkspaceTabs
        tasks={visibleTasks}
        activeTaskId={isPreviewActive ? previewActiveTaskId : activeTaskId}
        onSelectTask={handleSelectTask}
        onCloseTask={handleCloseTask}
        onNewTask={onNewTask}
      />
      <div className="flex min-h-0 flex-1">
        <div className="flex min-w-[400px] flex-1 flex-col border-r border-neutral-800">
          {visibleTask ? (
            <SummaryContent key={visibleTask.id} task={visibleTask} />
          ) : (
            <EmptyWorkspace
              onNewTask={onNewTask}
              onPreviewDemo={ENABLE_WORKSPACE_MOCK ? () => setPreviewMode(true) : undefined}
            />
          )}
        </div>
        <div className="flex w-[500px] flex-col bg-[#141414] xl:w-[600px]">
          <VideoChatPanel task={visibleTask || null} />
        </div>
      </div>
    </div>
  )
}
