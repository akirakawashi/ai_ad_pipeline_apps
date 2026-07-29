import { useEffect, useRef, useState } from 'react'

/**
 * Поле даты со своим календарём.
 *
 * Зачем не `<input type="date">`: его выпадающий календарь рисует **браузер**,
 * а не страница. До него не достаёт ни один селектор — он приезжает системным,
 * белым, с чужими шрифтами и чужой сеткой, и посреди тёмного интерфейса
 * выглядит как окно другой программы. Стилизовать там можно только само поле.
 *
 * Контракт снаружи тот же, что у нативного поля: значение — строка
 * «ГГГГ-ММ-ДД», пустая строка означает «не выбрано». Поэтому места вызова
 * ничего не пересчитывают, а разбор дат по-прежнему живёт в `formatters.ts`.
 *
 * Арифметика — на числах года, месяца и дня, без разбора строк через `new
 * Date(строка)`: такую строку стандарт велит понимать как UTC, и западнее
 * Гринвича выбранное число уехало бы на сутки назад (см. §10 AGENTS.md).
 */

const MONTHS = [
  'Январь',
  'Февраль',
  'Март',
  'Апрель',
  'Май',
  'Июнь',
  'Июль',
  'Август',
  'Сентябрь',
  'Октябрь',
  'Ноябрь',
  'Декабрь',
]

// Неделя с понедельника: у нас так принято, а getDay() считает с воскресенья.
const WEEKDAYS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']

// Шесть строк по семь дней — всегда. Сетка переменной высоты дёргала бы подвал
// вверх-вниз при листании: в феврале четыре строки, в марте с воскресеньем — шесть.
const WEEKS = 6
const CELLS = WEEKS * 7

interface Ymd {
  year: number
  month: number
  day: number
}

/** День сетки: сам по себе и признак «из соседнего месяца». */
interface Cell extends Ymd {
  outside: boolean
}

function parse(value: string): Ymd | null {
  const [year, month, day] = value.split('-').map(Number)
  if (!year || !month || !day) return null
  return { year, month, day }
}

function format(value: Ymd): string {
  const month = String(value.month).padStart(2, '0')
  const day = String(value.day).padStart(2, '0')
  return `${value.year}-${month}-${day}`
}

/** Для показа человеку: ДД.ММ.ГГГГ. */
function human(value: string): string {
  const parsed = parse(value)
  if (parsed === null) return ''
  const month = String(parsed.month).padStart(2, '0')
  const day = String(parsed.day).padStart(2, '0')
  return `${day}.${month}.${parsed.year}`
}

function todayYmd(): Ymd {
  const now = new Date()
  return { year: now.getFullYear(), month: now.getMonth() + 1, day: now.getDate() }
}

/** Понедельник — 0. Нужен, чтобы первое число встало в свою колонку. */
function weekdayIndex(year: number, month: number, day: number): number {
  return (new Date(year, month - 1, day).getDay() + 6) % 7
}

function daysInMonth(year: number, month: number): number {
  // Нулевой день следующего месяца — последний день этого. Конструктор сам
  // разбирается с високосными годами и переходом через декабрь.
  return new Date(year, month, 0).getDate()
}

function shiftMonth(year: number, month: number, delta: number): [number, number] {
  const zeroBased = year * 12 + (month - 1) + delta
  return [Math.floor(zeroBased / 12), (zeroBased % 12) + 1]
}

/** Сравнение дат как чисел: 2026-04-15 → 20260415. Порядок сохраняется. */
function ordinal(value: Ymd): number {
  return value.year * 10_000 + value.month * 100 + value.day
}

/**
 * Сетка месяца: хвост предыдущего, сам месяц, начало следующего.
 *
 * Соседние дни показываем, а не оставляем пустоты: неделя на стыке месяцев
 * иначе выглядит оборванной, и непонятно, 31-е это пятница или там просто дыра.
 */
function monthCells(year: number, month: number): Cell[] {
  const offset = weekdayIndex(year, month, 1)
  const total = daysInMonth(year, month)
  const [prevYear, prevMonth] = shiftMonth(year, month, -1)
  const [nextYear, nextMonth] = shiftMonth(year, month, 1)
  const prevTotal = daysInMonth(prevYear, prevMonth)

  const cells: Cell[] = []
  for (let back = offset; back > 0; back -= 1) {
    cells.push({
      year: prevYear,
      month: prevMonth,
      day: prevTotal - back + 1,
      outside: true,
    })
  }
  for (let day = 1; day <= total; day += 1) {
    cells.push({ year, month, day, outside: false })
  }
  for (let day = 1; cells.length < CELLS; day += 1) {
    cells.push({ year: nextYear, month: nextMonth, day, outside: true })
  }
  return cells
}

function outOfRange(value: Ymd, min?: string, max?: string): boolean {
  const current = ordinal(value)
  const lower = min ? parse(min) : null
  const upper = max ? parse(max) : null
  if (lower && current < ordinal(lower)) return true
  if (upper && current > ordinal(upper)) return true
  return false
}

interface DateFieldProps {
  /** «ГГГГ-ММ-ДД» либо пустая строка. */
  value: string
  onChange: (value: string) => void
  /** Подпись слева от поля — как у нативного варианта в форме. */
  label?: string
  placeholder?: string
  disabled?: boolean
  /** Границы выбора, «ГГГГ-ММ-ДД». Дни за ними видны, но не нажимаются. */
  min?: string
  max?: string
  /** Показывать ли «Очистить». У обязательной даты очистки быть не должно. */
  clearable?: boolean
  ariaLabel?: string
}

export function DateField({
  value,
  onChange,
  label,
  placeholder = 'Выберите дату',
  disabled = false,
  min,
  max,
  clearable = true,
  ariaLabel,
}: DateFieldProps) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)

  const selected = parse(value)
  const today = todayYmd()
  // Календарь открывается на месяце выбранной даты, а если её нет — на текущем.
  const [view, setView] = useState(() => {
    const start = selected ?? today
    return { year: start.year, month: start.month }
  })

  // Месяц выставляем в обработчике клика, а не эффектом на `open`: иначе
  // первый кадр открытого календаря показывал бы месяц, где бросили листать в
  // прошлый раз, и только потом перескакивал на нужный.
  const toggle = () => {
    if (!open) {
      const start = parse(value) ?? todayYmd()
      setView({ year: start.year, month: start.month })
    }
    setOpen(!open)
  }

  // Клик мимо и Escape закрывают. Слушаем, только пока открыто: подписка на
  // документ живёт ровно столько, сколько нужна.
  useEffect(() => {
    if (!open) return

    const onPointerDown = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false)
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }

    document.addEventListener('mousedown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('mousedown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open])

  const pick = (cell: Cell) => {
    onChange(format(cell))
    setOpen(false)
  }

  const goToday = () => {
    if (outOfRange(today, min, max)) return
    onChange(format(today))
    setOpen(false)
  }

  const clear = () => {
    onChange('')
    setOpen(false)
  }

  const step = (delta: number) => {
    const [year, month] = shiftMonth(view.year, view.month, delta)
    setView({ year, month })
  }

  const cells = monthCells(view.year, view.month)

  return (
    <div className="date-field" ref={rootRef}>
      {label && <span className="date-field-label">{label}</span>}
      <button
        type="button"
        className={`date-field-trigger${open ? ' is-open' : ''}${
          value ? '' : ' is-empty'
        }`}
        disabled={disabled}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={ariaLabel ?? label}
        onClick={toggle}
      >
        <span>{value ? human(value) : placeholder}</span>
        <span className="date-field-icon" aria-hidden="true">
          ▤
        </span>
      </button>

      {open && (
        <div className="date-popover" role="dialog" aria-label="Выбор даты">
          <header className="date-popover-head">
            <span className="date-popover-title">
              {MONTHS[view.month - 1]} {view.year}
            </span>
            <span className="date-nav-group">
              <button
                type="button"
                className="date-nav"
                aria-label="Предыдущий месяц"
                onClick={() => step(-1)}
              >
                ‹
              </button>
              <button
                type="button"
                className="date-nav"
                aria-label="Следующий месяц"
                onClick={() => step(1)}
              >
                ›
              </button>
            </span>
          </header>

          <div className="date-weekdays" aria-hidden="true">
            {WEEKDAYS.map((name) => (
              <span key={name}>{name}</span>
            ))}
          </div>

          <div className="date-grid">
            {cells.map((cell) => {
              const isSelected = selected !== null && ordinal(selected) === ordinal(cell)
              const isToday = ordinal(today) === ordinal(cell)
              return (
                <button
                  key={format(cell)}
                  type="button"
                  className={`date-cell${cell.outside ? ' is-outside' : ''}${
                    isSelected ? ' is-selected' : ''
                  }${isToday && !isSelected ? ' is-today' : ''}`}
                  disabled={outOfRange(cell, min, max)}
                  aria-current={isToday ? 'date' : undefined}
                  onClick={() => pick(cell)}
                >
                  {cell.day}
                </button>
              )
            })}
          </div>

          <footer className="date-popover-foot">
            {clearable && value ? (
              <button type="button" className="date-action" onClick={clear}>
                Очистить
              </button>
            ) : (
              <span />
            )}
            <button
              type="button"
              className="date-action"
              disabled={outOfRange(today, min, max)}
              onClick={goToday}
            >
              Сегодня
            </button>
          </footer>
        </div>
      )}
    </div>
  )
}
