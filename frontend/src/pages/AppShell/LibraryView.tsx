import { useEffect, useMemo, useState } from 'react'
import {
  Filter,
  Folder,
  FolderOpen,
  MoreVertical,
  PlayCircle,
  Plus,
  Search,
  Trash2,
} from 'lucide-react'
import type { Task } from '@/store/taskStore'
import { isMockBackend, isMockLikeTask, useTaskStore } from '@/store/taskStore'
import { get_task_status, type TaskStatusResponse } from '@/services/note'
import { getNoteRaw, getVideo, listVideos, type VideoItem } from '@/services/video'
import { formatDate, formatTime, getTaskAuthor, getTaskCoverUrl, getTaskTitle } from './utils'

interface LibraryFolder {
  id: string
  name: string
}

interface LibraryViewProps {
  onSelectTask: (taskId: string) => void
}

const FOLDER_STORAGE_KEY = 'aivideo-library-folders'
const ITEM_FOLDER_STORAGE_KEY = 'aivideo-library-item-folders'

function loadJson<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key)
    return raw ? (JSON.parse(raw) as T) : fallback
  } catch {
    return fallback
  }
}

const statusLabel: Record<string, string> = {
  PENDING: '排队中',
  PARSING: '解析链接',
  DOWNLOADING: '下载音频',
  TRANSCRIBING: '转写文字',
  SUMMARIZING: '总结内容',
  FORMATTING: '整理格式',
  SAVING: '保存结果',
  SUCCESS: '已完成',
  FAILED: '失败',
  RUNNING: '处理中',
}

function normalizeVideoStatus(status: string): Task['status'] {
  const value = status.toLowerCase()
  if (value === 'completed' || value === 'success' || value === 'stored') return 'SUCCESS'
  if (value === 'failed') return 'FAILED'
  if (value === 'pending') return 'PENDING'
  if (value === 'downloading') return 'DOWNLOADING'
  if (value === 'transcribing') return 'TRANSCRIBING'
  if (value === 'generating') return 'SUMMARIZING'
  if (value === 'storing') return 'SAVING'
  return 'RUNNING'
}

type BackendTaskResult = NonNullable<TaskStatusResponse['result']>

function hasTranscript(task: Task): boolean {
  return Boolean(task.transcript?.full_text || task.transcript?.segments?.length)
}

function mergeRawInfo(rawInfo: unknown, video: VideoItem) {
  const rawRecord = rawInfo && typeof rawInfo === 'object' ? rawInfo : {}
  return {
    ...rawRecord,
    uploader: video.uploader || (rawRecord as { uploader?: unknown }).uploader || '',
    bvid: video.bvid || (rawRecord as { bvid?: unknown }).bvid || '',
    backend_video: video,
  }
}

function backendVideoToTask(
  video: VideoItem,
  markdown: string,
  options: {
    id?: string
    result?: BackendTaskResult | null
    status?: Task['status']
  } = {},
): Task {
  const resultAudioMeta = options.result?.audio_meta
  const baseAudioMeta: Task['audioMeta'] = {
    cover_url: video.cover_url || '',
    duration: video.duration_seconds || 0,
    file_path: video.audio_path || '',
    platform: 'bilibili',
    raw_info: {
      uploader: video.uploader || '',
      bvid: video.bvid || '',
      backend_video: video,
    },
    title: video.title || video.url,
    video_id: video.video_id,
    source_url: video.source_url || video.url,
    player_url: video.player_url || null,
    embed_url: video.embed_url || null,
    chapters: video.chapters || [],
  }

  return {
    id: options.id || video.video_id,
    status: options.status || normalizeVideoStatus(video.status),
    markdown:
      options.result?.markdown ||
      markdown ||
      `# ${video.title || '后端视频笔记'}\n\n后端已返回视频记录，笔记原文暂未返回。`,
    transcript: options.result?.transcript || {
      full_text: '',
      language: 'zh-CN',
      raw: null,
      segments: [],
    },
    audioMeta: {
      ...baseAudioMeta,
      ...resultAudioMeta,
      raw_info: mergeRawInfo(resultAudioMeta?.raw_info || baseAudioMeta.raw_info, video),
      title: resultAudioMeta?.title || baseAudioMeta.title,
      video_id: resultAudioMeta?.video_id || baseAudioMeta.video_id,
      source_url: resultAudioMeta?.source_url || baseAudioMeta.source_url,
      player_url: resultAudioMeta?.player_url || baseAudioMeta.player_url,
      embed_url: resultAudioMeta?.embed_url || baseAudioMeta.embed_url,
      chapters: resultAudioMeta?.chapters || baseAudioMeta.chapters,
    },
    createdAt: video.created_at || new Date().toISOString(),
    formData: {
      video_url: video.source_url || video.url,
      link: true,
      screenshot: false,
      platform: 'bilibili',
      quality: '1080p',
      model_name: isMockBackend ? 'mock-backend' : 'backend',
      provider_id: isMockBackend ? 'mock-backend' : 'backend',
      format: ['summary'],
      style: 'minimal',
    },
  }
}

function findExistingVideoTask(video: VideoItem, tasks: Task[]): Task | undefined {
  return tasks.find(task =>
    task.id === video.video_id ||
    task.audioMeta?.video_id === video.video_id ||
    task.formData?.video_url === video.url ||
    task.formData?.video_url === video.source_url
  )
}

function latestTaskId(video: VideoItem): string | null {
  const tasks = video.tasks || []
  const completedTask = tasks.find(task =>
    ['completed', 'success'].includes(String(task.status || '').toLowerCase()),
  )
  return completedTask?.task_id || tasks[0]?.task_id || null
}

async function loadBackendTaskResult(video: VideoItem): Promise<{
  taskId: string | null
  result: BackendTaskResult | null
  status?: Task['status']
}> {
  if (!isMockBackend) return { taskId: null, result: null }

  const detailedVideo =
    video.tasks?.length
      ? video
      : await getVideo(video.video_id, { silent: true }).catch(() => video)
  const taskId = latestTaskId(detailedVideo)
  if (!taskId) return { taskId: null, result: null }

  const task = await get_task_status(taskId).catch(() => null)
  return {
    taskId,
    result: task?.result || null,
    status: task?.status,
  }
}

function mergeBackendTask(existing: Task | undefined, incoming: Task): Task {
  if (!existing) return incoming

  return {
    ...existing,
    ...incoming,
    id: existing.id,
    markdown: incoming.markdown || existing.markdown,
    transcript: hasTranscript(incoming) ? incoming.transcript : existing.transcript,
    audioMeta: {
      ...existing.audioMeta,
      ...incoming.audioMeta,
      raw_info: (incoming.audioMeta?.raw_info || existing.audioMeta?.raw_info || {}),
    },
  }
}

export default function LibraryView({ onSelectTask }: LibraryViewProps) {
  const storedTasks = useTaskStore(state => state.tasks)
  const removeTask = useTaskStore(state => state.removeTask)
  const upsertTask = useTaskStore(state => state.upsertTask)
  const [selectedFolderId, setSelectedFolderId] = useState<string | null>(null)
  const [folders, setFolders] = useState<LibraryFolder[]>(() =>
    loadJson<LibraryFolder[]>(FOLDER_STORAGE_KEY, [{ id: 'default', name: '默认收藏' }]),
  )
  const [itemFolders, setItemFolders] = useState<Record<string, string | null>>(() =>
    loadJson<Record<string, string | null>>(ITEM_FOLDER_STORAGE_KEY, {}),
  )
  const [isCreatingFolder, setIsCreatingFolder] = useState(false)
  const [newFolderName, setNewFolderName] = useState('')
  const [openMenuId, setOpenMenuId] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [backendSyncing, setBackendSyncing] = useState(false)
  const [backendSyncFailed, setBackendSyncFailed] = useState(false)
  const tasks = useMemo(
    () => (isMockBackend ? storedTasks : storedTasks.filter(task => !isMockLikeTask(task))),
    [storedTasks],
  )

  useEffect(() => {
    localStorage.setItem(FOLDER_STORAGE_KEY, JSON.stringify(folders))
  }, [folders])

  useEffect(() => {
    localStorage.setItem(ITEM_FOLDER_STORAGE_KEY, JSON.stringify(itemFolders))
  }, [itemFolders])

  useEffect(() => {
    let cancelled = false

    const syncBackendVideos = async () => {
      setBackendSyncing(true)
      setBackendSyncFailed(false)
      try {
        const res = await listVideos({ page: 1, page_size: 50 }, { silent: true })
        await Promise.all(
          res.items.map(async video => {
            const currentTasks = useTaskStore.getState().tasks
            const existingTask = findExistingVideoTask(video, currentTasks)
            const taskResult = await loadBackendTaskResult(video)
            const markdown =
              video.status === 'completed' || video.status === 'stored'
                ? await getNoteRaw(video.video_id, { silent: true }).catch(() => '')
                : ''
            const task = backendVideoToTask(video, markdown, {
              id: existingTask?.id || taskResult.taskId || video.video_id,
              result: taskResult.result,
              status: taskResult.status,
            })
            if (!cancelled) {
              upsertTask(mergeBackendTask(existingTask, task))
              // 移除重复任务（同一视频但 ID 不同的旧任务）
              const state = useTaskStore.getState()
              const duplicates = state.tasks.filter(t =>
                t.id !== task.id &&
                (t.audioMeta?.video_id === task.audioMeta?.video_id ||
                 t.formData?.video_url === task.formData?.video_url) &&
                t.formData?.video_url
              )
              for (const dup of duplicates) {
                state.removeTask(dup.id)
              }
            }
          }),
        )
      } catch {
        if (!cancelled) setBackendSyncFailed(true)
      } finally {
        if (!cancelled) setBackendSyncing(false)
      }
    }

    syncBackendVideos()
    return () => {
      cancelled = true
    }
  }, [upsertTask])

  const displayedTasks = useMemo(() => {
    const keyword = search.trim().toLowerCase()
    return tasks.filter(task => {
      const folderMatched =
        selectedFolderId === null ? true : itemFolders[task.id] === selectedFolderId
      if (!folderMatched) return false
      if (!keyword) return true
      return (
        getTaskTitle(task).toLowerCase().includes(keyword) ||
        getTaskAuthor(task).toLowerCase().includes(keyword) ||
        task.formData.video_url.toLowerCase().includes(keyword)
      )
    })
  }, [tasks, selectedFolderId, itemFolders, search])

  const folderItemCounts = useMemo(() => {
    return tasks.reduce<Record<string, number>>((counts, task) => {
      const folderId = itemFolders[task.id]
      if (!folderId) return counts
      counts[folderId] = (counts[folderId] ?? 0) + 1
      return counts
    }, {})
  }, [tasks, itemFolders])

  const handleCreateFolder = () => {
    const name = newFolderName.trim()
    if (!name) return
    setFolders(prev => [...prev, { id: crypto.randomUUID(), name }])
    setNewFolderName('')
    setIsCreatingFolder(false)
  }

  const updateItemFolder = (taskId: string, folderId: string | null) => {
    setItemFolders(prev => ({ ...prev, [taskId]: folderId }))
  }

  const handleDeleteFolder = (folder: LibraryFolder) => {
    const itemCount = folderItemCounts[folder.id] ?? 0
    const message =
      itemCount > 0
        ? `删除文件夹「${folder.name}」？其中 ${itemCount} 条笔记会移出文件夹，但不会被删除。`
        : `删除文件夹「${folder.name}」？`
    if (!window.confirm(message)) return

    setFolders(prev => prev.filter(item => item.id !== folder.id))
    setItemFolders(prev => {
      const next = { ...prev }
      Object.entries(next).forEach(([taskId, folderId]) => {
        if (folderId === folder.id) next[taskId] = null
      })
      return next
    })
    if (selectedFolderId === folder.id) setSelectedFolderId(null)
  }

  return (
    <div className="flex h-full flex-1 flex-col bg-[#0E0E0E]">
      <div className="flex h-20 shrink-0 items-center justify-between border-b border-neutral-800 bg-[#111111] px-8">
        <div>
          <h1 className="text-2xl font-bold text-neutral-100">知识库</h1>
          <div className="mt-1 text-xs text-neutral-500">
            {backendSyncing
              ? '正在同步后端视频...'
              : backendSyncFailed
                ? '后端视频同步失败'
                : `共 ${tasks.length} 条记录`}
          </div>
        </div>
        <div className="flex items-center gap-4">
          <div className="relative">
            <Search
              size={16}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-500"
            />
            <input
              type="text"
              value={search}
              onChange={event => setSearch(event.target.value)}
              placeholder="搜索笔记..."
              className="w-64 rounded-full border border-neutral-800 bg-[#1A1A1A] py-2 pl-9 pr-4 text-sm text-neutral-200 focus:border-neutral-600 focus:outline-none"
            />
          </div>
          <button
            type="button"
            className="rounded-full border border-neutral-800 bg-[#1A1A1A] p-2 text-neutral-400 transition-colors hover:text-neutral-200"
            aria-label="筛选"
          >
            <Filter size={18} />
          </button>
        </div>
      </div>

      <div className="flex min-h-0 flex-1 overflow-hidden">
        <div className="flex w-64 flex-col gap-2 overflow-y-auto border-r border-neutral-800 bg-[#111111] p-4">
          <button
            type="button"
            onClick={() => setSelectedFolderId(null)}
            className={`flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
              selectedFolderId === null
                ? 'bg-[#222222] text-neutral-200'
                : 'text-neutral-400 hover:bg-[#1A1A1A] hover:text-neutral-200'
            }`}
          >
            <FolderOpen size={16} />
            所有笔记
          </button>

          <div className="mb-2 mt-4 flex items-center justify-between px-3">
            <span className="text-xs font-bold text-neutral-500">本地文件夹</span>
            <button
              type="button"
              onClick={() => setIsCreatingFolder(true)}
              className="text-neutral-500 transition-colors hover:text-neutral-300"
              aria-label="新建文件夹"
            >
              <Plus size={14} />
            </button>
          </div>

          {isCreatingFolder && (
            <div className="mb-2 px-3 py-1">
              <input
                type="text"
                value={newFolderName}
                onChange={event => setNewFolderName(event.target.value)}
                onKeyDown={event => {
                  if (event.key === 'Enter') handleCreateFolder()
                  if (event.key === 'Escape') setIsCreatingFolder(false)
                }}
                autoFocus
                placeholder="文件夹名称..."
                className="w-full rounded border border-neutral-800 bg-[#1A1A1A] p-1.5 text-xs text-neutral-200 focus:border-neutral-500 focus:outline-none"
              />
            </div>
          )}

          {folders.map(folder => (
            <div
              key={folder.id}
              className={`group/folder flex items-center rounded-lg text-sm transition-colors ${
                selectedFolderId === folder.id
                  ? 'bg-[#222222] font-medium text-neutral-200'
                  : 'text-neutral-400 hover:bg-[#1A1A1A] hover:text-neutral-200'
              }`}
            >
              <button
                type="button"
                onClick={() => setSelectedFolderId(folder.id)}
                className="flex min-w-0 flex-1 items-center gap-2 rounded-l-lg px-3 py-2 text-left"
              >
                <Folder size={16} />
                <span className="truncate">{folder.name}</span>
              </button>
              <button
                type="button"
                onClick={() => handleDeleteFolder(folder)}
                className="mr-1 flex h-7 w-7 shrink-0 items-center justify-center rounded text-neutral-600 opacity-0 transition-all hover:bg-red-500/10 hover:text-red-400 focus:opacity-100 group-hover/folder:opacity-100"
                aria-label={`删除文件夹 ${folder.name}`}
                title="删除文件夹"
              >
                <Trash2 size={14} />
              </button>
            </div>
          ))}
        </div>

        <div
          className="custom-scrollbar relative flex-1 overflow-y-auto p-8"
          onClick={() => setOpenMenuId(null)}
        >
          {displayedTasks.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center text-neutral-500">
              <div className="mb-6 flex h-24 w-24 items-center justify-center rounded-full bg-neutral-800/50">
                <PlayCircle size={40} className="text-neutral-600" />
              </div>
              <h3 className="mb-2 text-lg font-medium text-neutral-300">
                {selectedFolderId ? '该文件夹为空' : '知识库暂无内容'}
              </h3>
              <p className="text-sm">提交视频链接生成笔记后，会自动出现在这里。</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {displayedTasks.map(task => (
                <TaskCard
                  key={task.id}
                  task={task}
                  folders={folders}
                  folderId={itemFolders[task.id] || null}
                  openMenu={openMenuId === task.id}
                  onOpenMenu={() => setOpenMenuId(openMenuId === task.id ? null : task.id)}
                  onSelect={() => onSelectTask(task.id)}
                  onMove={folderId => updateItemFolder(task.id, folderId)}
                  onRemove={() => removeTask(task.id)}
                />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function TaskCard({
  task,
  folders,
  folderId,
  openMenu,
  onOpenMenu,
  onSelect,
  onMove,
  onRemove,
}: {
  task: Task
  folders: LibraryFolder[]
  folderId: string | null
  openMenu: boolean
  onOpenMenu: () => void
  onSelect: () => void
  onMove: (folderId: string | null) => void
  onRemove: () => void
}) {
  const coverUrl = getTaskCoverUrl(task)
  const title = getTaskTitle(task)
  const author = getTaskAuthor(task) || task.formData.platform
  const duration = formatTime(task.audioMeta?.duration || 0)
  const createdAt = formatDate(task.createdAt)

  return (
    <div
      className={`group relative cursor-pointer rounded-2xl border border-neutral-800 bg-[#161616] transition-colors hover:border-neutral-600 ${
        openMenu ? 'z-30 overflow-visible' : 'overflow-hidden'
      }`}
      onClick={onSelect}
    >
      <div className="relative aspect-video overflow-hidden rounded-t-2xl border-b border-neutral-800/50 bg-black">
        {coverUrl ? (
          <img
            src={coverUrl}
            alt={title}
            referrerPolicy="no-referrer"
            className="h-full w-full object-cover opacity-80 transition-transform duration-500 group-hover:scale-105"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-neutral-700">
            <PlayCircle size={32} />
          </div>
        )}
        <div className="absolute bottom-2 right-2 rounded bg-black/80 px-2 py-1 font-mono text-xs text-white backdrop-blur-sm">
          {duration}
        </div>
      </div>
      <div className="relative p-4">
        <div className="mb-2 flex items-start justify-between gap-3">
          <h3 className="line-clamp-2 font-bold leading-snug text-neutral-200 transition-colors group-hover:text-primary">
            {title}
          </h3>
          <button
            type="button"
            className="shrink-0 rounded p-1 text-neutral-500 hover:bg-neutral-800 hover:text-neutral-300"
            onClick={event => {
              event.stopPropagation()
              onOpenMenu()
            }}
            aria-label="更多"
          >
            <MoreVertical size={16} />
          </button>
        </div>

        <div className="mt-4 flex items-center justify-between gap-3">
          <span className="truncate rounded bg-neutral-800/50 px-2 py-1 text-xs text-neutral-500">
            {author}
          </span>
          <span className="shrink-0 text-xs text-neutral-500">{createdAt}</span>
        </div>

        <div className="mt-3 flex items-center justify-between">
          <span
            className={`rounded px-2 py-0.5 text-xs ${
              task.status === 'SUCCESS'
                ? 'bg-primary/10 text-primary'
                : task.status === 'FAILED'
                  ? 'bg-red-500/10 text-red-400'
                  : 'bg-neutral-800 text-neutral-400'
            }`}
          >
            {statusLabel[task.status] || '处理中'}
          </span>
        </div>

        {openMenu && (
          <div
            className="absolute right-4 top-10 z-10 w-52 rounded-xl border border-neutral-700 bg-[#1A1A1A] py-1 shadow-2xl"
            onClick={event => event.stopPropagation()}
          >
            <div className="mb-1 border-b border-neutral-800 px-3 py-2 text-xs font-bold text-neutral-500">
              移动到本地文件夹...
            </div>
            <button
              type="button"
              onClick={() => onMove(null)}
              className={`flex w-full items-center justify-between px-4 py-2 text-left text-sm transition-colors hover:bg-neutral-800 ${
                folderId === null ? 'text-primary' : 'text-neutral-300'
              }`}
            >
              取消归档 {folderId === null && <span>✓</span>}
            </button>
            {folders.map(folder => (
              <button
                type="button"
                key={folder.id}
                onClick={() => onMove(folder.id)}
                className={`flex w-full items-center justify-between px-4 py-2 text-left text-sm transition-colors hover:bg-neutral-800 ${
                  folderId === folder.id ? 'text-primary' : 'text-neutral-300'
                }`}
              >
                <span className="truncate">{folder.name}</span>
                {folderId === folder.id && <span>✓</span>}
              </button>
            ))}
            <div className="my-1 border-t border-neutral-800" />
            <button
              type="button"
              onClick={onRemove}
              className="flex w-full items-center gap-2 px-4 py-2 text-left text-sm text-red-400 transition-colors hover:bg-red-500/10"
            >
              <Trash2 size={14} />
              删除任务
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
