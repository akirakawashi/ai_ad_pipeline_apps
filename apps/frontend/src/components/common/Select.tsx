import { useEffect, useId, useRef, useState } from 'react'

export interface SelectOption {
  value: string
  label: string
}

interface SelectProps {
  value: string
  options: SelectOption[]
  onChange: (value: string) => void
  placeholder?: string
  disabled?: boolean
  ariaLabel?: string
}

const CLOSE_ANIMATION_MS = 160

export function Select({
  value,
  options,
  onChange,
  placeholder = 'Выберите…',
  disabled,
  ariaLabel,
}: SelectProps) {
  const [open, setOpen] = useState(false)
  const [mounted, setMounted] = useState(false)
  const [highlighted, setHighlighted] = useState(0)
  const rootRef = useRef<HTMLDivElement>(null)
  const listRef = useRef<HTMLUListElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const closeTimer = useRef<number | undefined>(undefined)
  const baseId = useId()

  const selectedIndex = options.findIndex((option) => option.value === value)
  const selectedOption = selectedIndex >= 0 ? options[selectedIndex] : undefined

  const openList = () => {
    if (disabled || options.length === 0) return
    window.clearTimeout(closeTimer.current)
    setHighlighted(selectedIndex >= 0 ? selectedIndex : 0)
    setMounted(true)
    requestAnimationFrame(() => setOpen(true))
  }

  const closeList = () => {
    setOpen(false)
    closeTimer.current = window.setTimeout(() => setMounted(false), CLOSE_ANIMATION_MS)
  }

  useEffect(() => () => window.clearTimeout(closeTimer.current), [])

  useEffect(() => {
    if (!mounted) return
    const handlePointerDown = (event: PointerEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        closeList()
      }
    }
    document.addEventListener('pointerdown', handlePointerDown)
    return () => document.removeEventListener('pointerdown', handlePointerDown)
  }, [mounted])

  useEffect(() => {
    if (!open) return
    const item = listRef.current?.children[highlighted] as HTMLElement | undefined
    item?.scrollIntoView({ block: 'nearest' })
  }, [open, highlighted])

  const commit = (index: number) => {
    const option = options[index]
    if (!option) return
    if (option.value !== value) onChange(option.value)
    closeList()
    triggerRef.current?.focus()
  }

  const handleTriggerKeyDown = (event: React.KeyboardEvent) => {
    if (disabled) return
    if (!open) {
      if (['Enter', ' ', 'ArrowDown', 'ArrowUp'].includes(event.key)) {
        event.preventDefault()
        openList()
      }
      return
    }
    switch (event.key) {
      case 'ArrowDown':
        event.preventDefault()
        setHighlighted((index) => Math.min(index + 1, options.length - 1))
        break
      case 'ArrowUp':
        event.preventDefault()
        setHighlighted((index) => Math.max(index - 1, 0))
        break
      case 'Home':
        event.preventDefault()
        setHighlighted(0)
        break
      case 'End':
        event.preventDefault()
        setHighlighted(options.length - 1)
        break
      case 'Enter':
      case ' ':
        event.preventDefault()
        commit(highlighted)
        break
      case 'Escape':
        event.preventDefault()
        closeList()
        break
      case 'Tab':
        closeList()
        break
    }
  }

  return (
    <div className={`dropdown${open ? ' is-open' : ''}`} ref={rootRef}>
      <button
        ref={triggerRef}
        type="button"
        className="dropdown-trigger"
        disabled={disabled}
        role="combobox"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={`${baseId}-listbox`}
        aria-activedescendant={
          open && options[highlighted] ? `${baseId}-option-${highlighted}` : undefined
        }
        aria-label={ariaLabel}
        onClick={() => (open ? closeList() : openList())}
        onKeyDown={handleTriggerKeyDown}
      >
        <span className={`dropdown-value${selectedOption ? '' : ' is-placeholder'}`}>
          {selectedOption ? selectedOption.label : placeholder}
        </span>
        <svg
          className="dropdown-chevron"
          width="10"
          height="6"
          viewBox="0 0 10 6"
          fill="none"
          aria-hidden="true"
        >
          <path
            d="M1 1L5 5L9 1"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </button>
      {mounted && (
        <ul
          id={`${baseId}-listbox`}
          className={`dropdown-list${open ? ' is-open' : ''}`}
          role="listbox"
          ref={listRef}
        >
          {options.map((option, index) => (
            <li
              key={option.value}
              id={`${baseId}-option-${index}`}
              role="option"
              aria-selected={option.value === value}
              className={`dropdown-option${option.value === value ? ' is-selected' : ''}${
                index === highlighted ? ' is-highlighted' : ''
              }`}
              onMouseEnter={() => setHighlighted(index)}
              onClick={() => commit(index)}
            >
              <svg
                className="dropdown-option-check"
                width="12"
                height="9"
                viewBox="0 0 12 9"
                fill="none"
                aria-hidden="true"
              >
                <path
                  d="M1 4.5L4.2 7.5L11 1"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
              <span>{option.label}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
