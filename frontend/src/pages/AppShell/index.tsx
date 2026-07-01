import { useEffect, useMemo, useState } from 'react'
import { useTaskStore } from '@/store/taskStore'
import GenerateView from './GenerateView'
import LibraryView from './LibraryView'
import SettingsView from './SettingsView'
import ShellSidebar from './ShellSidebar'
import WorkspaceView from './WorkspaceView'
import type { ShellView } from './utils'

interface AppShellProps {
  initialView?: ShellView
  backendReady?: boolean
  backendFailed?: boolean
  backendLastError?: string | null
  onBackendRetry?: () => void
}

export default function AppShell({
  initialView = 'generate',
  backendReady = true,
  backendFailed = false,
  backendLastError = null,
  onBackendRetry,
}: AppShellProps) {
  const [currentView, setCurrentView] = useState<ShellView>(initialView)
  const [openTaskIds, setOpenTaskIds] = useState<string[]>([])
  const tasks = useTaskStore(state => state.tasks)
  const currentTaskId = useTaskStore(state => state.currentTaskId)
  const setCurrentTask = useTaskStore(state => state.setCurrentTask)

  useEffect(() => {
    setCurrentView(initialView)
  }, [initialView])

  const activeTask = useMemo(
    () => tasks.find(task => task.id === currentTaskId) || null,
    [tasks, currentTaskId],
  )

  const openTasks = useMemo(
    () =>
      openTaskIds
        .map(taskId => tasks.find(task => task.id === taskId))
        .filter((task): task is NonNullable<typeof task> => Boolean(task)),
    [openTaskIds, tasks],
  )

  useEffect(() => {
    if (!activeTask?.id) return
    setOpenTaskIds(prev =>
      prev.includes(activeTask.id) ? prev : [...prev, activeTask.id],
    )
  }, [activeTask?.id])

  useEffect(() => {
    if (tasks.length === 0) return
    const availableTaskIds = new Set(tasks.map(task => task.id))
    setOpenTaskIds(prev => prev.filter(taskId => availableTaskIds.has(taskId)))
  }, [tasks])

  useEffect(() => {
    if (currentTaskId && tasks.some(task => task.id === currentTaskId)) return
    if (openTasks[0]?.id) {
      setCurrentTask(openTasks[0].id)
    }
  }, [currentTaskId, openTasks, setCurrentTask, tasks])

  const handleOpenTask = (taskId: string) => {
    setOpenTaskIds(prev => (prev.includes(taskId) ? prev : [...prev, taskId]))
    setCurrentTask(taskId)
    setCurrentView('summary')
  }

  const handleCloseTask = (taskId: string) => {
    const nextOpenTaskIds = openTaskIds.filter(id => id !== taskId)
    if (currentTaskId === taskId) {
      const currentIndex = openTaskIds.indexOf(taskId)
      const fallbackTaskId =
        openTaskIds[currentIndex + 1] || openTaskIds[currentIndex - 1] || nextOpenTaskIds[0] || null
      setCurrentTask(fallbackTaskId)
    }
    setOpenTaskIds(nextOpenTaskIds)
  }

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-[#0E0E0E] font-sans text-neutral-200">
      <ShellSidebar currentView={currentView} onChangeView={setCurrentView} />

      <main className="relative flex-1 overflow-hidden bg-[#0E0E0E]">
        <div
          className={`absolute inset-0 flex flex-col ${currentView === 'generate' ? 'z-10' : 'hidden z-0'}`}
        >
          <GenerateView
            backendReady={backendReady}
            onSubmitted={() => setCurrentView('summary')}
            onOpenSettings={() => setCurrentView('settings')}
          />
        </div>

        <div
          className={`absolute inset-0 flex flex-col ${currentView === 'library' ? 'z-10' : 'hidden z-0'}`}
        >
          <LibraryView onSelectTask={handleOpenTask} />
        </div>

        <div
          className={`absolute inset-0 flex flex-col ${currentView === 'settings' ? 'z-10' : 'hidden z-0'}`}
        >
          <SettingsView
            backendReady={backendReady}
            backendFailed={backendFailed}
            backendLastError={backendLastError}
            onBackendRetry={onBackendRetry}
          />
        </div>

        <div
          className={`absolute inset-0 flex ${currentView === 'summary' ? 'z-10' : 'hidden z-0'}`}
        >
          <WorkspaceView
            task={activeTask}
            openTasks={openTasks}
            activeTaskId={currentTaskId}
            onSelectTask={handleOpenTask}
            onCloseTask={handleCloseTask}
            onNewTask={() => setCurrentView('generate')}
          />
        </div>
      </main>
    </div>
  )
}
