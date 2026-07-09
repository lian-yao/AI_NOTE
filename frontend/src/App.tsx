import './App.css'
import { lazy, Suspense, useEffect } from 'react'
import { BrowserRouter, HashRouter, Navigate, Routes, Route } from 'react-router-dom'
import { useTaskPolling } from '@/hooks/useTaskPolling.ts'
import { useCheckBackend } from '@/hooks/useCheckBackend.ts'
import { systemCheck } from '@/services/system.ts'
import BackendInitDialog from '@/components/BackendInitDialog'
import StartupBanner from '@/components/SystemDiagnostic/StartupBanner'
import Index from '@/pages/Index.tsx'
import AppShell from '@/pages/AppShell'
import { hasCompletedOnboarding } from '@/utils/onboarding'

// 非首屏页面使用 React.lazy 按需加载
const Onboarding = lazy(() => import('@/pages/Onboarding'))
const BackendLogWindow = lazy(() => import('@/components/BackendHealth/BackendLogWindow'))

// 桌面端首启引导守卫：未完成 onboarding 时强制跳到 /onboarding
function OnboardingGuard({ children }: { children: React.ReactNode }) {
  const isTauri = typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window
  // 仅在 Tauri 桌面端拦截；纯 web 端不打扰用户
  if (!isTauri) return <>{children}</>
  if (!hasCompletedOnboarding()) return <Navigate to="/onboarding" replace />
  return <>{children}</>
}
const NotFoundPage = lazy(() => import('@/pages/NotFoundPage'))

function App() {
  const isBackendLogRoute = typeof window !== 'undefined'
    && (window.location.hash.includes('/backend-logs') || window.location.pathname.includes('/backend-logs'))
  const { loading, initialized, failed, lastError, retry } = useCheckBackend()
  useTaskPolling(3000, initialized && !isBackendLogRoute) // 每 3 秒轮询一次

  // 在后端初始化完成后执行系统检查
  useEffect(() => {
    if (initialized && !isBackendLogRoute) {
      systemCheck()
    }
  }, [initialized, isBackendLogRoute])

  // 桌面端使用 HashRouter 避免刷新 404；Web 端继续使用 BrowserRouter
  const isTauri = typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window
  const Router = isTauri ? HashRouter : BrowserRouter

  // 主应用立即渲染；后端启动状态以非阻塞浮层提示
  return (
    <>
      {!isBackendLogRoute && <StartupBanner />}
      {!isBackendLogRoute && <BackendInitDialog open={loading && !initialized && !failed} />}
      <Router>
        <Suspense fallback={<div className="flex h-screen items-center justify-center">加载中…</div>}>
          <Routes>
            <Route path="/onboarding" element={<Onboarding />} />
            <Route path="/backend-logs" element={<BackendLogWindow />} />
            <Route path="/" element={<OnboardingGuard><Index /></OnboardingGuard>}>
            <Route
              index
              element={
                <AppShell
                  backendReady={initialized}
                  backendFailed={failed}
                  backendLastError={lastError}
                  onBackendRetry={retry}
                />
              }
            />
            <Route
              path="settings/*"
              element={
                <AppShell
                  initialView="settings"
                  backendReady={initialized}
                  backendFailed={failed}
                  backendLastError={lastError}
                  onBackendRetry={retry}
                />
              }
            />
              <Route path="*" element={<NotFoundPage />} />
            </Route>
          </Routes>
        </Suspense>
      </Router>
    </>
  )
}

export default App
