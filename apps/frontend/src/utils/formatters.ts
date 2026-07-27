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

/** Обратное преобразование: UTC-ISO с сервера → значение для поля ввода. */
export function localInputFromIso(value: string | null): string {
  if (!value) return ''
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return ''
  const offset = parsed.getTimezoneOffset() * 60_000
  return new Date(parsed.getTime() - offset).toISOString().slice(0, 16)
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

export function pluralVideos(count: number) {
  return plural(count, 'видео', 'видео', 'видео')
}
