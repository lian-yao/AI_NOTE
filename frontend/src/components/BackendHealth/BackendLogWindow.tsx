import BackendLogPanel from './BackendLogPanel'
import { useBackendEvents } from './useBackendEvents'

const BackendLogWindow = () => {
  const { status, exitCode, logs, restart, copyLogs, isTauri } = useBackendEvents()
  const health = status === 'terminated' ? 'red' : 'green'

  async function closeWindow() {
    if (!isTauri) return
    const { getCurrentWebviewWindow } = await import('@tauri-apps/api/webviewWindow')
    await getCurrentWebviewWindow().close()
  }

  return (
    <BackendLogPanel
      status={status}
      exitCode={exitCode}
      logs={logs}
      health={health}
      onRestart={restart}
      onCopyLogs={copyLogs}
      onClose={closeWindow}
      variant="window"
    />
  )
}

export default BackendLogWindow
