import type { Aggregate, MetricStat } from '../types'

export function formatDuration(value: number | null) {
  if (!value) return '—'
  const minutes = Math.floor(value / 60)
  const seconds = Math.round(value % 60)
  return `${minutes}:${String(seconds).padStart(2, '0')}`
}

export function formatBytes(value: number) {
  if (value < 1024 ** 2) return `${Math.round(value / 1024)} KB`
  return `${(value / 1024 ** 2).toFixed(1)} MB`
}

export function formatNumber(value: number | undefined) {
  return value === undefined
    ? '—'
    : new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 }).format(value)
}

/** Выбранная оценка центра из величины «на съёмку». */
export function statValue(value: MetricStat, aggregate: Aggregate): number {
  return aggregate === 'median' ? value.median : value.mean
}

/**
 * Величина «на съёмку» для плитки: выбранная оценка плюс разброс между
 * съёмками. Разброс показываем при обеих оценках — он про то, насколько
 * разошлись проезды, а не про то, каким способом их свернули.
 */
export function formatStat(
  value: MetricStat,
  aggregate: Aggregate,
  digits = 1,
): string {
  const center = statValue(value, aggregate)
  if (!center) return '—'
  const text = formatNumber(Number(center.toFixed(digits)))
  if (!value.std) return text
  return `${text} ± ${value.std.toFixed(digits)}`
}

/**
 * <input type="datetime-local"> отдаёт «2026-08-01T09:30» без зоны. Отправлять
 * такое на сервер нельзя: колонка timestamptz, и наивное время истолкуется по
 * зоне сессии базы, а не браузера. Поэтому переводим в UTC-ISO явно.
 */
export function isoFromLocalInput(value: string): string | null {
  if (!value) return null
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? null : parsed.toISOString()
}

/**
 * «ГГГГ-ММ-ДД» → ISO полуночи по МЕСТНОМУ времени, со сдвигом на dayOffset суток.
 *
 * Через `new Date('2026-05-03')` нельзя: такую строку стандарт велит понимать
 * как UTC, и западнее Гринвича полученный момент попал бы на предыдущие сутки —
 * человек выбрал бы третье, а на сервер уехало бы второе. Собираем из чисел,
 * потому что конструктор с числами считает время местным.
 *
 * Сутки сдвигаем номером дня, а не миллисекундами: конструктор сам перекатывает
 * месяц и год, а «плюс 86 400 000 мс» промахнулся бы в день перевода часов.
 */
function localMidnight(value: string, dayOffset: number): string | null {
  if (!value) return null
  const [year, month, day] = value.split('-').map(Number)
  if (!year || !month || !day) return null
  const parsed = new Date(year, month - 1, day + dayOffset)
  return Number.isNaN(parsed.getTime()) ? null : parsed.toISOString()
}

/** Начало выбранного дня — включающая граница периода. */
export function isoFromDateInput(value: string): string | null {
  return localMidnight(value, 0)
}

/**
 * Начало СЛЕДУЮЩЕГО дня — так включающий конец периода становится исключающей
 * границей: «по 31 мая» значит «строго раньше 1 июня», и съёмка в 23:50
 * последнего дня остаётся внутри окна.
 */
export function isoFromDateInputExclusiveEnd(value: string): string | null {
  return localMidnight(value, 1)
}

/** Обратное преобразование: UTC-ISO с сервера → значение для поля ввода. */
export function localInputFromIso(value: string | null): string {
  if (!value) return ''
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return ''
  const offset = parsed.getTimezoneOffset() * 60_000
  return new Date(parsed.getTime() - offset).toISOString().slice(0, 16)
}

/** Значение календарного поля «ГГГГ-ММ-ДД» → короткая подпись «ДД.ММ.ГГГГ». */
export function formatDateInput(value: string): string {
  const [year, month, day] = value.split('-').map(Number)
  if (!year || !month || !day) return value
  return `${String(day).padStart(2, '0')}.${String(month).padStart(2, '0')}.${year}`
}

export function formatDateTime(value: string | null): string {
  if (!value) return '—'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return '—'
  return new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(parsed)
}

/** Окно «начало — конец». Прочерк, если не заполнено ни то, ни другое. */
export function formatPeriod(from: string | null, to: string | null): string {
  if (!from && !to) return '—'
  return `${formatDateTime(from)} — ${formatDateTime(to)}`
}

/** Русское склонение: (1) задание, (2) задания, (5) заданий. */
function plural(count: number, one: string, few: string, many: string): string {
  const mod10 = count % 10
  const mod100 = count % 100
  if (mod10 === 1 && mod100 !== 11) return `${count} ${one}`
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) {
    return `${count} ${few}`
  }
  return `${count} ${many}`
}

export function pluralAssignments(count: number) {
  return plural(count, 'задание', 'задания', 'заданий')
}

export function pluralRoutes(count: number) {
  return plural(count, 'маршрут', 'маршрута', 'маршрутов')
}

export function pluralShootings(count: number) {
  return plural(count, 'съёмка', 'съёмки', 'съёмок')
}

export function pluralZones(count: number) {
  return plural(count, 'участок', 'участка', 'участков')
}
