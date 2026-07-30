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
  /** Относительная ширина каждой вкладки, если подписи заметно разной длины. */
  optionWeights?: number[]
}

export function Tabs({
  value,
  options,
  onChange,
  ariaLabel,
  optionWeights,
}: TabsProps) {
  const activeIndex = Math.max(
    0,
    options.findIndex((option) => option.value === value),
  )
  const weights =
    optionWeights?.length === options.length &&
    optionWeights.every((weight) => weight > 0)
      ? optionWeights
      : null
  const totalWeight = weights?.reduce((sum, weight) => sum + weight, 0) ?? 0
  const activeStart = weights
    ? weights.slice(0, activeIndex).reduce((sum, weight) => sum + weight, 0) /
      totalWeight
    : 0
  const activeWidth = weights ? weights[activeIndex] / totalWeight : 0
  const indicatorStyle = weights
    ? {
        left: `calc(${activeStart * 100}% + ${4 - activeStart * 8}px)`,
        width: `calc(${activeWidth * 100}% - ${activeWidth * 8}px)`,
        transform: 'none',
      }
    : { transform: `translateX(${activeIndex * 100}%)` }

  return (
    <div
      className="tabs"
      role="tablist"
      aria-label={ariaLabel}
      style={
        {
          '--tabs-count': options.length,
          gridTemplateColumns: weights
            ? weights.map((weight) => `${weight}fr`).join(' ')
            : undefined,
        } as CSSProperties
      }
    >
      <div className="tabs-indicator" style={indicatorStyle} />
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
