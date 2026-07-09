const BACKEND_LOG_WINDOW_LABEL = 'backend-logs'

export async function openBackendLogWindow() {
  const isTauri = typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window
  if (!isTauri) return false

  const { WebviewWindow } = await import('@tauri-apps/api/webviewWindow')
  const existing = await WebviewWindow.getByLabel(BACKEND_LOG_WINDOW_LABEL)
  if (existing) {
    await existing.unminimize().catch(() => undefined)
    await existing.show().catch(() => undefined)
    await existing.setFocus().catch(() => undefined)
    return true
  }

  new WebviewWindow(BACKEND_LOG_WINDOW_LABEL, {
    url: '/#/backend-logs',
    title: '后端日志',
    width: 920,
    height: 640,
    minWidth: 680,
    minHeight: 420,
    center: true,
    focus: true,
    resizable: true,
    decorations: true,
    backgroundColor: '#0E0E0E',
  })

  return true
}
