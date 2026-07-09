import { lazy, Suspense, useEffect, useMemo, useState } from 'react'
import { isMockBackend, isMockLikeTask, useTaskStore } from '@/store/taskStore'
import GenerateView from './GenerateView'
import GlobalQA from './GlobalQA'
import ShellSidebar from './ShellSidebar'
import type { ShellView } from './utils'

const loadLibraryView = () => import('./LibraryView')
const loadSettingsView = () => import('./SettingsView')
const loadWorkspaceView = () => import('./WorkspaceView')

const LibraryView = lazy(loadLibraryView)
const SettingsView = lazy(loadSettingsView)
const WorkspaceView = lazy(loadWorkspaceView)

interface AppShellProps {
  initialView?: ShellView
  backendReady?: boolean
  backendFailed?: boolean
  backendLastError?: string | null
  onBackendRetry?: () => void
}

function GenericViewFallback() {
  return (
    <div className="flex h-full w-full flex-1 items-center justify-center bg-[#0E0E0E] text-sm text-neutral-500">
      <div className="flex items-center gap-2 rounded-lg border border-neutral-800 bg-[#141414] px-4 py-2 shadow-2xl">
        <span className="h-2 w-2 animate-pulse rounded-full bg-primary" />
        <span>正在加载视图...</span>
      </div>
    </div>
  )
}

function WorkspaceViewFallback() {
  return (
    <div className="flex h-full w-full flex-1 flex-col bg-[#0E0E0E] text-neutral-500">
      <div className="flex h-12 shrink-0 items-center border-b border-neutral-800 bg-[#101010] px-3">
        <div className="h-7 w-40 animate-pulse rounded-t-lg bg-neutral-800/80" />
        <div className="ml-2 h-7 w-28 animate-pulse rounded-t-lg bg-neutral-900" />
      </div>
      <div className="flex min-h-0 flex-1">
        <div className="flex min-w-[400px] flex-1 flex-col border-r border-neutral-800 bg-[#111111]">
          <div className="flex h-14 shrink-0 items-center gap-6 border-b border-neutral-800 px-4">
            <div className="h-4 w-16 animate-pulse rounded bg-neutral-800" />
            <div className="h-4 w-16 animate-pulse rounded bg-neutral-800/60" />
            <div className="h-4 w-16 animate-pulse rounded bg-neutral-800/60" />
          </div>
          <div className="border-b border-neutral-800/50 bg-[#161616] px-6 py-4">
            <div className="h-3 w-36 animate-pulse rounded bg-neutral-800" />
          </div>
          <div className="custom-scrollbar flex-1 overflow-hidden px-6 pt-8">
            <div className="mx-auto max-w-3xl space-y-5">
              <div className="h-7 w-2/3 animate-pulse rounded bg-neutral-800" />
              <div className="space-y-3">
                <div className="h-3 w-full animate-pulse rounded bg-neutral-800/80" />
                <div className="h-3 w-11/12 animate-pulse rounded bg-neutral-800/70" />
                <div className="h-3 w-4/5 animate-pulse rounded bg-neutral-800/60" />
              </div>
              <div className="mt-8 space-y-3">
                <div className="h-4 w-44 animate-pulse rounded bg-neutral-800" />
                <div className="h-3 w-full animate-pulse rounded bg-neutral-800/70" />
                <div className="h-3 w-10/12 animate-pulse rounded bg-neutral-800/60" />
              </div>
            </div>
          </div>
        </div>
        <div className="flex w-[500px] flex-col bg-[#141414] xl:w-[600px]">
          <div className="aspect-video shrink-0 border-b border-neutral-800 bg-neutral-950">
            <div className="flex h-full items-center justify-center">
              <div className="h-10 w-10 animate-pulse rounded-full bg-neutral-800" />
            </div>
          </div>
          <div className="space-y-3 border-b border-neutral-800 p-4">
            <div className="h-5 w-2/3 animate-pulse rounded bg-neutral-800" />
            <div className="h-3 w-1/3 animate-pulse rounded bg-neutral-800/70" />
          </div>
          <div className="flex min-h-0 flex-1 flex-col bg-[#161616]">
            <div className="h-10 shrink-0 border-b border-neutral-800 bg-[#1A1A1A]" />
            <div className="flex flex-1 items-center justify-center text-sm text-neutral-500">
              正在准备工作区...
            </div>
          </div>
        </div>
      </div>
    </div>
  )
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
  const storedTasks = useTaskStore(state => state.tasks)
  const currentTaskId = useTaskStore(state => state.currentTaskId)
  const setCurrentTask = useTaskStore(state => state.setCurrentTask)
  const tasks = useMemo(
    () => (isMockBackend ? storedTasks : storedTasks.filter(task => !isMockLikeTask(task))),
    [storedTasks],
  )

  useEffect(() => {
    setCurrentView(initialView)
  }, [initialView])

  useEffect(() => {
    const id = window.setTimeout(() => {
      loadWorkspaceView()
    }, 800)
    return () => window.clearTimeout(id)
  }, [])

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

  const handlePreviewView = (view: ShellView) => {
    if (view === 'summary') loadWorkspaceView()
    if (view === 'library') loadLibraryView()
    if (view === 'settings') loadSettingsView()
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
      <ShellSidebar
        currentView={currentView}
        onChangeView={setCurrentView}
        onPreviewView={handlePreviewView}
      />

      <main className="relative flex-1 overflow-hidden bg-[#0E0E0E]">
        {currentView === 'generate' && (
          <div className="absolute inset-0 z-10 flex flex-col">
            <GenerateView
              backendReady={backendReady}
              onSubmitted={() => setCurrentView('summary')}
              onOpenSettings={() => setCurrentView('settings')}
            />
          </div>
        )}

        {currentView === 'library' && (
          <div className="absolute inset-0 z-10 flex flex-col">
            <Suspense fallback={<GenericViewFallback />}>
              <LibraryView onSelectTask={handleOpenTask} />
            </Suspense>
          </div>
        )}

        {currentView === 'settings' && (
          <div className="absolute inset-0 z-10 flex flex-col">
            <Suspense fallback={<GenericViewFallback />}>
              <SettingsView
                backendReady={backendReady}
                backendFailed={backendFailed}
                backendLastError={backendLastError}
                onBackendRetry={onBackendRetry}
              />
            </Suspense>
          </div>
        )}

        {currentView === 'summary' && (
          <div className="absolute inset-0 z-10 flex">
            <Suspense fallback={<WorkspaceViewFallback />}>
              <WorkspaceView
                task={activeTask}
                openTasks={openTasks}
                activeTaskId={currentTaskId}
                onSelectTask={handleOpenTask}
                onCloseTask={handleCloseTask}
                onNewTask={() => setCurrentView('generate')}
              />
            </Suspense>
          </div>
        )}
        {currentView === 'qa' && (
          <div className='absolute inset-0 z-10 flex flex-col'>
            <GlobalQA />
          </div>
        )}
      </main>
    </div>
  )
}
