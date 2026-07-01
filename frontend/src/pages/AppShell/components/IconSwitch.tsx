type IconSwitchProps = {
  checked: boolean
  disabled?: boolean
  label: string
  onClick: () => void
  size?: 'sm' | 'md'
}

export function IconSwitch({ checked, disabled, label, onClick, size = 'md' }: IconSwitchProps) {
  const trackClass = size === 'sm' ? 'h-5 w-10' : 'h-6 w-11'
  const knobClass = size === 'sm' ? 'h-4 w-4' : 'h-5 w-5'

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      aria-pressed={checked}
      className={`relative inline-flex shrink-0 items-center overflow-hidden rounded-full border p-0.5 outline-none transition-[background-color,border-color,box-shadow] duration-200 focus-visible:ring-2 focus-visible:ring-primary/40 disabled:cursor-not-allowed disabled:opacity-50 ${trackClass} ${
        checked
          ? 'border-primary/40 bg-primary shadow-[inset_0_0_0_1px_rgba(255,255,255,0.18)]'
          : 'border-neutral-700 bg-neutral-800'
      }`}
    >
      <span
        className={`block rounded-full bg-white shadow-[0_1px_4px_rgba(0,0,0,0.35)] transition-transform duration-200 ease-out ${knobClass} ${
          checked ? 'translate-x-5' : 'translate-x-0'
        }`}
      />
    </button>
  )
}
