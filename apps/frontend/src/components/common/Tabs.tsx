import type { CSSProperties } from 'react'

export interface TabOption {
  value: string
  label: string
}

interface TabsProps {
  value: string
  options: TabOption[]
  onChange: (value: string) => void
  ariaLabel?: string
}

export function Tabs({ value, options, onChange, ariaLabel }: TabsProps) {
  const activeIndex = Math.max(
    0,
    options.findIndex((option) => option.value === value),
  )

  return (
    <div
      className="tabs"
      role="tablist"
      aria-label={ariaLabel}
      style={{ '--tabs-count': options.length } as CSSProperties}
    >
      <div
        className="tabs-indicator"
        style={{ transform: `translateX(${activeIndex * 100}%)` }}
      />
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          role="tab"
          aria-selected={option.value === value}
          className={`tabs-option${option.value === value ? ' is-active' : ''}`}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}
