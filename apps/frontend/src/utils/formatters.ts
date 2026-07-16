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

/** Русское склонение: (1) замер, (2) замера, (5) замеров. */
function plural(count: number, one: string, few: string, many: string): string {
  const mod10 = count % 10
  const mod100 = count % 100
  if (mod10 === 1 && mod100 !== 11) return `${count} ${one}`
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) {
    return `${count} ${few}`
  }
  return `${count} ${many}`
}

export function pluralMeasurements(count: number) {
  return plural(count, 'замер', 'замера', 'замеров')
}

export function pluralRoutes(count: number) {
  return plural(count, 'маршрут', 'маршрута', 'маршрутов')
}

export function pluralPasses(count: number) {
  return plural(count, 'проезд', 'проезда', 'проездов')
}

export function pluralVideos(count: number) {
  return plural(count, 'видео', 'видео', 'видео')
}
