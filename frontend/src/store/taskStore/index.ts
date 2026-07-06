import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'
import { delete_task, generateNote } from '@/services/note.ts'
import { retryBackendTask } from '@/services/task'
import { v4 as uuidv4 } from 'uuid'
import toast from 'react-hot-toast'
import { get, set, del } from 'idb-keyval'
import { getApiBaseURL } from '@/utils/api'


export type TaskStatus =
  | 'PENDING'
  | 'RUNNING'
  | 'PARSING'
  | 'DOWNLOADING'
  | 'TRANSCRIBING'
  | 'SUMMARIZING'
  | 'FORMATTING'
  | 'SAVING'
  | 'SUCCESS'
  | 'FAILED'
  | 'CANCELLED'

export interface AudioMeta {
  cover_url: string
  duration: number
  file_path: string
  platform: string
  raw_info: unknown
  title: string
  video_id: string
  source_url?: string
  player_url?: string | null
  embed_url?: string | null
  chapters?: Array<{
    title?: string
    start_time?: number
    end_time?: number
  }>
}

export interface Segment {
  start: number
  end: number
  text: string
}

export interface Transcript {
  full_text: string
  language: string
  raw: unknown
  segments: Segment[]
}
export interface Markdown {
  ver_id: string
  content: string
  style: string
  model_name: string
  created_at: string
}

export interface Task {
  id: string
  markdown: string | Markdown[] // 为了兼容之前的笔记
  transcript: Transcript
  status: TaskStatus
  audioMeta: AudioMeta
  createdAt: string
  formData: {
    video_url: string
    link: undefined | boolean
    screenshot: undefined | boolean
    platform: string
    quality: string
    model_name: string
    provider_id: string
    format?: string[]
    style?: string
    extras?: string
    video_understanding?: boolean
    video_interval?: number
    grid_size?: number[]
  }
}

interface TaskStore {
  tasks: Task[]
  currentTaskId: string | null
  addPendingTask: (taskId: string, platform: string, formData: Task['formData']) => void
  upsertTask: (task: Task) => void
  updateTaskContent: (id: string, data: Partial<Omit<Task, 'id' | 'createdAt'>>) => void
  removeTask: (id: string) => void
  clearTasks: () => void
  setCurrentTask: (taskId: string | null) => void
  getCurrentTask: () => Task | null
  retryTask: (id: string, payload?: Partial<Task['formData']>) => void
}

function storageSafeKey(value: string): string {
  return value.replace(/[^a-zA-Z0-9._-]+/g, '_').replace(/^_+|_+$/g, '')
}

const apiBaseURL = getApiBaseURL()
const explicitBackendMode = String(import.meta.env.VITE_BACKEND_MODE || '').toLowerCase()
export const isMockBackend =
  explicitBackendMode === 'mock' ||
  (explicitBackendMode !== 'real' && /(^|[:/])8010(\/|$)/.test(apiBaseURL))
const taskStorageName = `task-storage:${isMockBackend ? 'mock' : 'real'}:${storageSafeKey(apiBaseURL)}`
const legacyTaskStorageName = 'task-storage'

function valueFromRecord(value: unknown, key: string): string {
  if (!value || typeof value !== 'object') return ''
  const record = value as Record<string, unknown>
  const item = record[key]
  return typeof item === 'string' ? item : ''
}

export function isMockLikeTask(task: Task | undefined): boolean {
  if (!task) return false

  const title = task.audioMeta?.title || ''
  const rawInfo = task.audioMeta?.raw_info
  const backendVideo =
    rawInfo && typeof rawInfo === 'object'
      ? (rawInfo as { backend_video?: unknown }).backend_video
      : null
  const author = valueFromRecord(rawInfo, 'uploader')
  const videoId = task.audioMeta?.video_id || task.id || ''
  const sourceUrl = task.formData?.video_url || task.audioMeta?.source_url || ''
  const filePath = task.audioMeta?.file_path || ''
  const coverUrl = task.audioMeta?.cover_url || ''
  const providerId = task.formData?.provider_id || ''
  const modelName = task.formData?.model_name || ''
  const backendAudioPath = valueFromRecord(backendVideo, 'audio_path')
  const backendVideoPath = valueFromRecord(backendVideo, 'video_path')

  return (
    providerId === 'preview' ||
    providerId === 'mock-provider' ||
    providerId === 'mock-backend' ||
    modelName === 'mock-llm' ||
    modelName === 'mock-backend' ||
    sourceUrl.startsWith('preview://') ||
    filePath.includes('mock_backend') ||
    backendAudioPath.includes('mock_backend') ||
    backendVideoPath.includes('mock_backend') ||
    coverUrl.includes('/mock-cover/') ||
    videoId.includes('BV1Mock') ||
    title.startsWith('Bilibili demo') ||
    author === 'Mock Studio'
  )
}

function sanitizeStoredTaskValue(value: unknown): string | null {
  if (typeof value !== 'string') return null
  if (isMockBackend) return null

  try {
    const parsed = JSON.parse(value) as {
      state?: {
        tasks?: unknown
        currentTaskId?: unknown
      }
      version?: unknown
    }
    const state = parsed.state || {}
    const tasks = Array.isArray(state.tasks)
      ? state.tasks.filter(task => !isMockLikeTask(task as Task))
      : []
    const currentTaskId =
      typeof state.currentTaskId === 'string' &&
      tasks.some(task => (task as Task).id === state.currentTaskId)
        ? state.currentTaskId
        : null

    return JSON.stringify({
      ...parsed,
      state: {
        ...state,
        tasks,
        currentTaskId,
      },
    })
  } catch {
    return value
  }
}

async function migrateLegacyTaskStorage(name: string): Promise<string | null> {
  if (isMockBackend) return null

  const legacyValue = await get(legacyTaskStorageName)
  const migratedValue = sanitizeStoredTaskValue(legacyValue)
  if (!migratedValue) return null

  await set(name, migratedValue)
  await del(legacyTaskStorageName)
  return migratedValue
}

function persistableTaskState(state: TaskStore) {
  if (isMockBackend) {
    return {
      tasks: [],
      currentTaskId: null,
    }
  }

  const tasks = state.tasks.filter(task => !isMockLikeTask(task))
  const currentTaskId = tasks.some(task => task.id === state.currentTaskId)
    ? state.currentTaskId
    : null

  return {
    tasks,
    currentTaskId,
  }
}

export const useTaskStore = create<TaskStore>()(
  persist(
    (set, get) => ({
      tasks: [],
      currentTaskId: null,

      addPendingTask: (taskId: string, platform: string, formData: Task['formData']) =>

        set(state => ({
          tasks: [
            {
              formData: formData,
              id: taskId,
              status: 'PENDING',
              markdown: '',
              platform: platform,
              transcript: {
                full_text: '',
                language: '',
                raw: null,
                segments: [],
              },
              createdAt: new Date().toISOString(),
              audioMeta: {
                cover_url: '',
                duration: 0,
                file_path: '',
                platform: '',
                raw_info: null,
                title: '',
                video_id: '',
              },
            },
            ...state.tasks,
          ],
          currentTaskId: taskId, // 默认设置为当前任务
        })),

      upsertTask: task =>
        set(state => {
          const exists = state.tasks.some(item => item.id === task.id)
          return {
            tasks: exists
              ? state.tasks.map(item => (item.id === task.id ? { ...item, ...task } : item))
              : [task, ...state.tasks],
          }
        }),

      updateTaskContent: (id, data) =>
          set(state => ({
            tasks: state.tasks.map(task => {
              if (task.id !== id) return task

              if (task.status === 'SUCCESS' && data.status === 'SUCCESS') return task

              // 如果是 markdown 字符串，封装为版本
              if (typeof data.markdown === 'string') {
                const prev = task.markdown
                const newVersion: Markdown = {
                  ver_id: `${task.id}-${uuidv4()}`,
                  content: data.markdown,
                  style: task.formData.style || '',
                  model_name: task.formData.model_name || '',
                  created_at: new Date().toISOString(),
                }

                let updatedMarkdown: Markdown[]
                if (Array.isArray(prev)) {
                  updatedMarkdown = [newVersion, ...prev]
                } else {
                  updatedMarkdown = [
                    newVersion,
                    ...(typeof prev === 'string' && prev
                        ? [{
                          ver_id: `${task.id}-${uuidv4()}`,
                          content: prev,
                          style: task.formData.style || '',
                          model_name: task.formData.model_name || '',
                          created_at: new Date().toISOString(),
                        }]
                        : []),
                  ]
                }

                return {
                  ...task,
                  ...data,
                  markdown: updatedMarkdown,
                }
              }

              return { ...task, ...data }
            }),
          })),


      getCurrentTask: () => {
        const currentTaskId = get().currentTaskId
        return get().tasks.find(task => task.id === currentTaskId) || null
      },
      retryTask: async (id: string, payload?: Partial<Task['formData']>) => {

        if (!id){
          toast.error('任务不存在')
          return
        }
        const task = get().tasks.find(task => task.id === id)
        console.log('retry',task)
        if (!task) return

        const newFormData = {
          ...task.formData,
          ...payload,
        }
        try {
          if (task.status === 'FAILED') {
            try {
              await retryBackendTask(id, { silent: true })
              set(state => ({
                tasks: state.tasks.map(t =>
                  t.id === id
                    ? {
                      ...t,
                      status: 'PENDING',
                    }
                    : t,
                ),
              }))
              return
            } catch {
              // 本地合成任务或后端没有该任务时，继续走重新提交兜底。
            }
          }

          await generateNote({
            ...newFormData,
            task_id: id,
          })
        } catch (e: unknown) {
          // 就绪门禁：转写模型未下载好。不要把任务标成 PENDING（会一直转），
          // 给提示让用户先去下载。
          const reasonData = e && typeof e === 'object' && 'data' in e ? e.data : null
          const reason =
            reasonData && typeof reasonData === 'object' && 'reason' in reasonData
              ? reasonData.reason
              : undefined
          const downloading =
            reasonData && typeof reasonData === 'object' && 'downloading' in reasonData
              ? Boolean(reasonData.downloading)
              : false
          if (reason === 'transcriber_model_not_ready') {
            toast.error(
              downloading
                ? '转写模型正在下载中，请稍候再重试'
                : '转写模型尚未下载，请先去「设置 → 音频转写配置」页下载',
            )
            return
          }
          console.error('重试任务失败：', e)
          return
        }

        set(state => ({
          tasks: state.tasks.map(t =>
              t.id === id
                  ? {
                    ...t,
                    formData: newFormData, // ✅ 显式更新 formData
                    status: 'PENDING',
                  }
                  : t
          ),
        }))
      },


      removeTask: async id => {
        const task = get().tasks.find(t => t.id === id)

        // 更新 Zustand 状态
        set(state => ({
          tasks: state.tasks.filter(task => task.id !== id),
          currentTaskId: state.currentTaskId === id ? null : state.currentTaskId,
        }))

        // 调用后端删除接口（如果找到了任务）
        if (task) {
          await delete_task({
            video_id: task.audioMeta?.video_id || task.id,
            platform: task.formData?.platform || "",
          })
        }
      },

      cancelTask: async (id: string) => {
        const { tasks } = get()
        const task = tasks.find(t => t.id === id)
        if (!task) return
        // 标记为已取消，不再轮询
        set(state => ({
          tasks: state.tasks.filter(t => t.id !== id),
        }))
        try {
          const { cancelBackendTask } = await import('@/services/note')
          await cancelBackendTask(id)
          toast.success('任务已取消')
        } catch (e) {
          console.error('取消失败:', e)
        }
      },

      clearTasks: () => set({ tasks: [], currentTaskId: null }),

      setCurrentTask: taskId => set({ currentTaskId: taskId }),
    }),
    {
      name: taskStorageName,
      storage: createJSONStorage(() => ({
        getItem: async (name: string): Promise<string | null> => {
          const value = await get(name)
          const sanitizedValue = sanitizeStoredTaskValue(value)
          if (sanitizedValue) {
            if (sanitizedValue !== value) await set(name, sanitizedValue)
            return sanitizedValue
          }
          return migrateLegacyTaskStorage(name)
        },
        setItem: async (name: string, value: string): Promise<void> => {
          if (isMockBackend) {
            await del(name)
            return
          }
          await set(name, value)
        },
        removeItem: async (name: string): Promise<void> => {
          await del(name)
        },
      })),
      partialize: persistableTaskState,
    }
  )
)
