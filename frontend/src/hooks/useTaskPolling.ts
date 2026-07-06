import { useEffect, useRef } from 'react'
import { useTaskStore } from '@/store/taskStore'
import { get_task_status } from '@/services/note.ts'
import toast from 'react-hot-toast'

export const useTaskPolling = (interval = 3000, enabled = true) => {
  const tasks = useTaskStore(state => state.tasks)
  const updateTaskContent = useTaskStore(state => state.updateTaskContent)

  const tasksRef = useRef(tasks)
  const failureCountRef = useRef<Record<string, number>>({})

  // 每次 tasks 更新，把最新的 tasks 同步进去
  useEffect(() => {
    tasksRef.current = tasks
  }, [tasks])

  useEffect(() => {
    if (!enabled) return

    const timer = setInterval(async () => {
      const pendingTasks = tasksRef.current.filter(
        task => task.status != 'SUCCESS' && task.status != 'FAILED' && task.status != 'CANCELLED'
      )

      // 无活跃任务时跳过轮询
      if (pendingTasks.length === 0) return

      for (const task of pendingTasks) {
        try {
          const res = await get_task_status(task.id)
          const { status } = res
          failureCountRef.current[task.id] = 0

          if (status && status !== task.status) {
            if (status === 'SUCCESS') {
              if (!res.result) {
                updateTaskContent(task.id, { status: 'PENDING' })
                continue
              }

              const { markdown, transcript, audio_meta } = res.result
              toast.success('笔记生成成功')
              updateTaskContent(task.id, {
                status,
                ...(markdown !== undefined ? { markdown } : {}),
                ...(transcript !== undefined ? { transcript } : {}),
                ...(audio_meta !== undefined ? { audioMeta: audio_meta } : {}),
              })
            } else if (status === 'FAILED') {
              updateTaskContent(task.id, { status, message: res.message || '任务处理失败' })
              console.warn(`⚠️ 任务 ${task.id} 失败`)
            } else {
              updateTaskContent(task.id, { status, message: res.message || undefined })
            }
          }
        } catch (e) {
          console.error('❌ 任务轮询失败：', e)
          const nextFailureCount = (failureCountRef.current[task.id] || 0) + 1
          failureCountRef.current[task.id] = nextFailureCount
          if (nextFailureCount >= 3) {
            updateTaskContent(task.id, { status: 'FAILED', message: '任务状态查询失败' })
          }
        }
      }
    }, interval)

    return () => clearInterval(timer)
  }, [enabled, interval, updateTaskContent])
}
