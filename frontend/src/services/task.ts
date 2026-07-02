import request from '@/utils/request'

interface CallOpts {
  silent?: boolean
}

const cfg = (opts?: CallOpts) => (opts?.silent ? { suppressToast: true } : undefined)

export interface TaskLogItem {
  id?: number
  task_id?: string | number
  level: string
  message: string
  detail?: string | null
  created_at?: string
}

export interface TaskLogsResponse {
  items: TaskLogItem[]
  total: number
  page: number
  page_size: number
}

export interface RetryTaskResponse {
  task_id: string
  status: string
  retry_count: number
}

export const getTaskLogs = async (
  taskId: string,
  params: { level?: string; page?: number; page_size?: number } = {},
  opts?: CallOpts,
): Promise<TaskLogsResponse> => {
  return await request.get(`/tasks/${encodeURIComponent(taskId)}/logs`, {
    ...(cfg(opts) || {}),
    params,
  })
}

export const retryBackendTask = async (
  taskId: string,
  opts?: CallOpts,
): Promise<RetryTaskResponse> => {
  return await request.post(`/tasks/${encodeURIComponent(taskId)}/retry`, undefined, cfg(opts))
}
