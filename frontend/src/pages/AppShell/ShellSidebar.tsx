import { LayoutDashboard, Library, PlusCircle, Settings } from 'lucide-react'
import type { ComponentType } from 'react'
import type { ShellView } from './utils'

interface ShellSidebarProps {
  currentView: ShellView
  onChangeView: (view: ShellView) => void
}

const items: { view: ShellView; label: string; icon: ComponentType<{ size?: number }> }[] = [
  { view: 'generate', label: '新建', icon: PlusCircle },
  { view: 'summary', label: '工作区', icon: LayoutDashboard },
  { view: 'library', label: '知识库', icon: Library },
]

export default function ShellSidebar({ currentView, onChangeView }: ShellSidebarProps) {
  return (
    <aside className="z-10 flex h-full w-[68px] shrink-0 flex-col items-center border-r border-neutral-800 bg-[#111111] py-4">
      <div className="mt-4 flex w-full flex-col items-center gap-4">
        {items.map(item => {
          const Icon = item.icon
          const active = currentView === item.view
          const primary = item.view === 'generate'
          return (
            <button
              key={item.view}
              type="button"
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
              <span className="pointer-events-none absolute left-14 z-50 whitespace-nowrap rounded bg-neutral-800 px-2 py-1 text-xs text-neutral-200 opacity-0 shadow-xl transition-opacity group-hover:opacity-100">
                {item.label}
              </span>
            </button>
          )
        })}
      </div>

      <div className="mt-auto flex w-full flex-col items-center gap-4">
        <button
          type="button"
          onClick={() => onChangeView('settings')}
          className={`group relative flex h-10 w-10 items-center justify-center rounded-xl transition-colors ${
            currentView === 'settings'
              ? 'bg-neutral-800 text-neutral-200'
              : 'text-neutral-500 hover:bg-neutral-800 hover:text-neutral-300'
          }`}
          aria-label="设置"
        >
          <Settings size={20} />
          <span className="pointer-events-none absolute left-14 z-50 whitespace-nowrap rounded bg-neutral-800 px-2 py-1 text-xs text-neutral-200 opacity-0 shadow-xl transition-opacity group-hover:opacity-100">
            设置
          </span>
        </button>
      </div>
    </aside>
  )
}
