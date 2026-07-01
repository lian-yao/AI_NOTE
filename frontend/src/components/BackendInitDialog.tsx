import { useMemo, useState } from 'react'
import { AlertTriangle, Clipboard, Loader2, RotateCcw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useBackendEvents } from '@/components/BackendHealth/useBackendEvents'

const STDERR_PREVIEW_LINES = 4

interface Props {
  open: boolean
  failed?: boolean
  lastError?: string | null
  onRetry?: () => void
  placement?: 'floating' | 'inline'
}

function BackendInitDialog({
  open,
  failed = false,
  lastError = null,
  onRetry,
  placement = 'floating',
}: Props) {
  const { isTauri, restart, copyLogs, logs } = useBackendEvents()
  const [restarting, setRestarting] = useState(false)
  const [copyResult, setCopyResult] = useState<'idle' | 'ok' | 'fail'>('idle')

  const stderrPreview = useMemo(() => {
    if (!failed || !logs?.length) return []
    return logs
      .filter(log => log.level === 'error')
      .slice(-STDERR_PREVIEW_LINES)
      .map(log => log.text)
  }, [failed, logs])

  const isOpen = open || failed
  if (!isOpen) return null

  const handleRestart = async () => {
    setRestarting(true)
    try {
      if (isTauri) await restart()
      onRetry?.()
    } finally {
      setRestarting(false)
    }
  }

  const handleCopy = async () => {
    const ok = await copyLogs()
    setCopyResult(ok ? 'ok' : 'fail')
    setTimeout(() => setCopyResult('idle'), 2000)
  }

  if (failed) {
    const failedClassName =
      placement === 'inline'
        ? 'mb-4 rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-sm text-neutral-200'
        : 'fixed bottom-16 left-4 right-4 z-[9997] rounded-lg border border-red-500/30 bg-[#141414] p-4 text-sm text-neutral-200 shadow-2xl sm:left-auto sm:max-w-lg'

    return (
      <div
        role="status"
        aria-live="polite"
        className={failedClassName}
      >
        <div className="flex items-start gap-3">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-red-400" />
          <div className="min-w-0 flex-1">
            <div className="font-medium text-red-200">后端启动失败</div>
            <p className="mt-1 text-xs leading-5 text-neutral-400">
              {lastError || '后端在预计时间内未就绪，前端界面仍可继续开发和调试。'}
            </p>

            {stderrPreview.length > 0 && (
              <pre className="mt-3 max-h-24 overflow-auto rounded bg-zinc-950 px-2 py-1.5 font-mono text-[11px] leading-snug text-red-200">
                {stderrPreview.join('\n')}
              </pre>
            )}

            <div className="mt-3 flex flex-wrap gap-2">
              <Button size="sm" onClick={handleRestart} disabled={restarting} className="gap-1.5">
                {restarting ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <RotateCcw className="h-4 w-4" />
                )}
                {isTauri ? (restarting ? '重启中...' : '重启后端') : '重试连接'}
              </Button>
              {isTauri && (
                <Button size="sm" variant="outline" onClick={handleCopy} className="gap-1.5">
                  <Clipboard className="h-4 w-4" />
                  {copyResult === 'ok'
                    ? '已复制'
                    : copyResult === 'fail'
                      ? '复制失败'
                      : '复制日志'}
                </Button>
              )}
            </div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div
      role="status"
      aria-live="polite"
      className="pointer-events-none fixed bottom-16 left-4 right-4 z-[9997] rounded-lg border border-neutral-800 bg-[#111111]/95 p-4 text-sm text-neutral-200 shadow-2xl sm:left-auto sm:max-w-md"
    >
      <div className="flex items-start gap-3">
        <Loader2 className="mt-0.5 h-4 w-4 shrink-0 animate-spin text-primary" />
        <div className="min-w-0">
          <div className="font-medium">后端正在后台启动</div>
          <p className="mt-1 text-xs leading-5 text-neutral-400">
            主界面可继续操作；依赖服务的请求会在后端就绪后恢复。
          </p>
        </div>
      </div>
    </div>
  )
}

export default BackendInitDialog
