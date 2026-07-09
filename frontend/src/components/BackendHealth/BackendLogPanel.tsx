import { useEffect, useRef, useState } from 'react'
import { Copy, RefreshCcw, X } from 'lucide-react'
import type { LogEntry, BackendStatus } from './useBackendEvents'

interface Props {
  status: BackendStatus
  exitCode: number | null
  logs: LogEntry[]
  health: 'green' | 'yellow' | 'red' | 'unknown'
  onRestart: () => Promise<void>
  onCopyLogs: () => Promise<boolean>
  onClose?: () => void
  variant?: 'floating' | 'window'
}

const BackendLogPanel = ({
  status,
  exitCode,
  logs,
  health,
  onRestart,
  onCopyLogs,
  onClose,
  variant = 'floating',
}: Props) => {
  const [restarting, setRestarting] = useState(false)
  const [copied, setCopied] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)

  // 新日志进来自动滚到底
  useEffect(() => {
    if (scrollRef.current)
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
  }, [logs])

  async function handleRestart() {
    setRestarting(true)
    try { await onRestart() }
    catch { /* errors already in log via useBackendEvents */ }
    finally { setRestarting(false) }
  }

  async function handleCopy() {
    const ok = await onCopyLogs()
    setCopied(ok)
    setTimeout(() => setCopied(false), 1500)
  }

  const shellClass = variant === 'window'
    ? 'flex h-screen w-screen flex-col overflow-hidden bg-[#0E0E0E] text-neutral-200'
    : 'fixed bottom-4 right-4 top-16 z-[9999] flex w-[480px] max-w-[90vw] flex-col overflow-hidden rounded-xl border border-neutral-800 bg-[#111111] text-neutral-200 shadow-2xl shadow-black/50'

  return (
    <section className={shellClass}>
        <header className="flex items-center justify-between border-b border-neutral-800 bg-[#141414] px-4 py-3">
          <div>
            <h2 className="text-base font-semibold text-neutral-100">后端运行状态</h2>
            <div className="mt-0.5 text-xs text-neutral-500">
              {status === 'terminated'
                ? `已退出（退出码 ${exitCode ?? 'unknown'}）`
                : health === 'red'
                  ? '运行中但无响应'
                  : health === 'yellow'
                    ? '运行中，部分系统检查未通过'
                    : '运行正常'}
            </div>
          </div>
          {onClose && (
            <button
              className="flex h-8 w-8 items-center justify-center rounded-lg text-neutral-500 transition-colors hover:bg-neutral-800 hover:text-neutral-200"
              title="关闭日志窗口"
              onClick={onClose}
            >
              <X size={16} />
            </button>
          )}
        </header>

        <div className="flex items-center gap-2 border-b border-neutral-800 bg-[#101010] px-4 py-2">
          <button
            className="flex items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-primary/80 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={restarting}
            onClick={handleRestart}
          >
            <RefreshCcw size={14} className={restarting ? 'animate-spin' : ''} />
            {restarting ? '重启中…' : '重启后端'}
          </button>
          <button
            className="flex items-center gap-1.5 rounded-lg border border-neutral-800 bg-neutral-900 px-3 py-1.5 text-sm text-neutral-300 transition-colors hover:bg-neutral-800 hover:text-neutral-100"
            onClick={handleCopy}
          >
            <Copy size={14} />
            {copied ? '已复制' : '复制日志'}
          </button>
          <span className="ml-auto text-xs text-neutral-500">
            最近 {logs.length} 行
          </span>
        </div>

        <div
          ref={scrollRef}
          className="custom-scrollbar flex-1 overflow-auto bg-[#090909] p-3 font-mono text-xs text-neutral-100"
        >
          {logs.length === 0 ? (
            <div className="text-neutral-600 italic">暂无日志输出</div>
          ) : (
            logs.map((l, i) => (
              <div
                key={`${l.ts}-${i}`}
                className={`whitespace-pre-wrap break-all leading-snug ${l.level === 'error' ? 'text-red-300' : 'text-neutral-100'}`}
              >
                <span className="mr-2 text-neutral-600">
                  {new Date(l.ts).toISOString().slice(11, 19)}
                </span>
                {l.text}
              </div>
            ))
          )}
        </div>

        <footer className="border-t border-neutral-800 bg-[#101010] px-4 py-2 text-xs text-neutral-500">
          后端进程退出 / 无响应时，先点「重启后端」；仍不行复制日志去 issue 反馈。
        </footer>
    </section>
  )
}

export default BackendLogPanel
