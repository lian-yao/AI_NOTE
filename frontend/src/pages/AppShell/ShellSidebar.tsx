import { LayoutDashboard, Library, MessageCircle, PlusCircle, Settings } from 'lucide-react'
import type { ComponentType } from 'react'
import type { ShellView } from './utils'

interface ShellSidebarProps {
  currentView: ShellView
  onChangeView: (view: ShellView) => void
  onPreviewView?: (view: ShellView) => void
}

const items: { view: ShellView; label: string; icon: ComponentType<{ size?: number }> }[] = [
  { view: 'generate', label: '新建', icon: PlusCircle },
  { view: 'summary', label: '工作区', icon: LayoutDashboard },
  { view: 'library', label: '知识库', icon: Library },
  { view: 'qa', label: '全局问答', icon: MessageCircle },
]

function SidebarTooltip({ label }: { label: string }) {
  return (
    <span className="pointer-events-none absolute left-[calc(100%+12px)] top-1/2 z-[100] -translate-y-1/2 translate-x-1 whitespace-nowrap rounded-md border border-neutral-700 bg-neutral-900 px-2.5 py-1.5 text-xs font-medium text-neutral-100 opacity-0 shadow-2xl shadow-black/50 transition-[opacity,transform] duration-150 group-hover:translate-x-0 group-hover:opacity-100 group-focus-visible:translate-x-0 group-focus-visible:opacity-100">
      <span className="absolute left-[-4px] top-1/2 size-2 -translate-y-1/2 rotate-45 border-b border-l border-neutral-700 bg-neutral-900" />
      {label}
    </span>
  )
}

export default function ShellSidebar({
  currentView,
  onChangeView,
  onPreviewView,
}: ShellSidebarProps) {
  return (
    <aside className="relative z-50 flex h-full w-[68px] shrink-0 flex-col items-center overflow-visible border-r border-neutral-800 bg-[#111111] py-4">
      <div className="mt-4 flex w-full flex-col items-center gap-4">
        {items.map(item => {
          const Icon = item.icon
          const active = currentView === item.view
          const primary = item.view === 'generate'
          return (
            <button
              key={item.view}
              type="button"
              onFocus={() => onPreviewView?.(item.view)}
              onMouseEnter={() => onPreviewView?.(item.view)}
              onClick={() => onChangeView(item.view)}
              className={`group relative flex h-10 w-10 items-center justify-center rounded-xl transition-colors ${
                active
                  ? primary
                    ? 'bg-primary/20 text-primary'
                    : 'bg-neutral-800 text-neutral-200'
                  : primary
                    ? 'bg-primary/10 text-primary/70 hover:bg-primary/20 hover:text-primary'
                    : 'text-neutral-400 hover:bg-neutral-800 hover:text-neutral-200'
              }`}
              aria-label={item.label}
            >
              <Icon size={22} />
              <SidebarTooltip label={item.label} />
            </button>
          )
        })}
      </div>

      <div className="mt-auto flex w-full flex-col items-center gap-4">
        <button
          type="button"
          onFocus={() => onPreviewView?.('settings')}
          onMouseEnter={() => onPreviewView?.('settings')}
          onClick={() => onChangeView('settings')}
          className={`group relative flex h-10 w-10 items-center justify-center rounded-xl transition-colors ${
            currentView === 'settings'
              ? 'bg-neutral-800 text-neutral-200'
              : 'text-neutral-500 hover:bg-neutral-800 hover:text-neutral-300'
          }`}
          aria-label="设置"
        >
          <Settings size={20} />
          <SidebarTooltip label="设置" />
        </button>
      </div>
    </aside>
  )
}
