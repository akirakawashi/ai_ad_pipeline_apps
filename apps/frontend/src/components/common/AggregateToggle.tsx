import { Tabs } from './Tabs'
import type { Aggregate } from '../../types'

const OPTIONS = [
  { value: 'mean', label: 'Среднее' },
  { value: 'median', label: 'Медиана' },
]

/**
 * Чем сворачивать съёмки в одну цифру. Среднее слышит каждый проезд, медиана не
 * замечает выбросов: один проезд в пробке её не сдвинет, но и десятикратно
 * удачный тоже. Обе величины уже пришли с сервера — переключение ничего не
 * запрашивает и работает мгновенно.
 */
export function AggregateToggle({
  value,
  onChange,
}: {
  value: Aggregate
  onChange: (value: Aggregate) => void
}) {
  return (
    <Tabs
      value={value}
      options={OPTIONS}
      onChange={(next) => onChange(next as Aggregate)}
      ariaLabel="Как считать показатели за съёмку"
    />
  )
}
