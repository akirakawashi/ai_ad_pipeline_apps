import { useEffect, useRef, useState } from 'react'
import { Metric } from './common/Metric'
import { MetricsPanel } from './common/MetricsPanel'
import { DateField } from './common/DateField'
import { EmptyState } from './common/Feedback'
import { RollupCharts } from './RollupCharts'
import { RouteShootingsChart } from './RouteShootingsChart'
import { navigate, type RoutePeriod } from '../routing'
import type { Aggregate, RouteSummary } from '../types'
import {
  formatDateInput,
  formatDateTime,
  formatDuration,
  formatNumber,
  formatStat,
  pluralAssignments,
  pluralShootings,
} from '../utils/formatters'

/**
 * Окно отбора съёмок по дате. Обе границы включительно и обе необязательны:
 * «с начала по 31 мая» и «с 1 июня и дальше» — законные периоды.
 *
 * Отбор уходит на сервер, а не считается здесь: там же, где живёт единственная
 * реализация усреднения. Обе границы сначала меняются в черновике и уходят
 * одним запросом по «Применить», поэтому цифра за период не может разойтись с
 * цифрой без периода, а хранилище не перечитывается дважды.
 */
function PeriodPicker({
  period,
  onChange,
}: {
  period: RoutePeriod
  onChange: (period: RoutePeriod) => void
}) {
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState<RoutePeriod>(period)
  const rootRef = useRef<HTMLDivElement>(null)
  const filtered = Boolean(period.from || period.to)
  const setDraftPeriod = (patch: RoutePeriod) =>
    setDraft((current) => ({ ...current, ...patch }))

  const label = period.from
    ? period.to
      ? `${formatDateInput(period.from)} — ${formatDateInput(period.to)}`
      : `С ${formatDateInput(period.from)}`
    : period.to
      ? `По ${formatDateInput(period.to)}`
      : 'За всё время'

  const toggle = () => {
    if (open) {
      setOpen(false)
      return
    }
    // Каждый новый заход начинает с уже применённого окна: закрытый без
    // «Применить» черновик не должен неожиданно вернуться позже.
    setDraft(period)
    setOpen(true)
  }

  const apply = () => {
    setOpen(false)
    if (draft.from === period.from && draft.to === period.to) return
    onChange(draft)
  }

  const reset = () => {
    setDraft({})
    setOpen(false)
    if (filtered) onChange({})
  }

  // Внешний popover закрывается отдельно от календарей внутри. Клик по
  // календарю остаётся внутри rootRef, поэтому выбор дня не схлопывает всю
  // форму до нажатия «Применить».
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

  return (
    <div className="period-filter" ref={rootRef}>
      <div
        className={`period-filter-control${filtered ? ' has-reset' : ''}`}
      >
        <button
          type="button"
          className={`period-filter-trigger${filtered ? ' is-active' : ''}${
            open ? ' is-open' : ''
          }`}
          aria-haspopup="dialog"
          aria-expanded={open}
          onClick={toggle}
        >
          <span className="period-filter-icon" aria-hidden="true" />
          <span>{label}</span>
          <span className="period-filter-chevron" aria-hidden="true">
            ⌄
          </span>
        </button>
        {filtered && (
          <button
            type="button"
            className="period-filter-reset"
            aria-label="Сбросить период"
            onClick={reset}
          >
            ×
          </button>
        )}
      </div>

      {open && (
        <form
          className="period-filter-popover"
          role="dialog"
          aria-label="Период записи"
          onSubmit={(event) => {
            event.preventDefault()
            apply()
          }}
        >
          <header className="period-filter-popover-head">
            <h3>Период записи</h3>
            <p>Начальная и конечная даты входят в выбор.</p>
          </header>
          {/* Границы ограничивают друг друга: конец не выбрать раньше начала.
              Бэкенд ту же проверку делает заново — здесь она ради того, чтобы
              неверный период нельзя было даже набрать. */}
          <div className="period-filter-fields">
            <DateField
              label="с"
              ariaLabel="Начало периода"
              placeholder="с начала"
              value={draft.from ?? ''}
              max={draft.to}
              onChange={(next) =>
                setDraftPeriod({ from: next || undefined })
              }
            />
            <DateField
              label="по"
              ariaLabel="Конец периода"
              placeholder="по сегодня"
              value={draft.to ?? ''}
              min={draft.from}
              onChange={(next) => setDraftPeriod({ to: next || undefined })}
            />
          </div>
          <footer className="period-filter-actions">
            <button type="button" className="ghost-button" onClick={reset}>
              За всё время
            </button>
            <button type="submit" className="primary">
              Применить
            </button>
          </footer>
        </form>
      )}
    </div>
  )
}

/**
 * Метрики маршрута. Считаются из съёмок напрямую, поэтому и показываем съёмки:
 * средняя цифра без списка, из чего она собрана, врёт по умолчанию — задание из
 * одного проезда выглядит в ней так же уверенно, как задание из двадцати.
 */
export function RouteSummaryPanel({
  summary,
  period,
  onPeriodChange,
  aggregate,
  onAggregateChange,
}: {
  summary: RouteSummary
  period: RoutePeriod
  onPeriodChange: (period: RoutePeriod) => void
  // Оценка приходит со страницы, а не заводится здесь: панель живёт под
  // вкладкой и размонтируется при уходе на задания, а выбранная медиана это
  // пережить должна.
  aggregate: Aggregate
  onAggregateChange: (value: Aggregate) => void
}) {
  const { totals, brands, shootings, assignments_total } = summary
  const waiting = totals.shootings_total - totals.shootings_completed
  const filtered = Boolean(period.from || period.to)

  // Заголовка «Аналитика маршрута» здесь нет: так теперь называется вкладка,
  // под которой лежит вся панель, и повторять её строкой ниже незачем.
  const heading = (
    <header className="route-summary-head route-analytics-head">
      <PeriodPicker period={period} onChange={onPeriodChange} />
    </header>
  )

  if (totals.shootings_completed === 0) {
    return (
      <>
        {heading}
        <EmptyState
          text={
            filtered
              ? 'За выбранный период видео нет. Расширьте окно или сбросьте его.'
              : waiting > 0
                ? `Метрики маршрута появятся, когда обработается первое видео. Сейчас в работе ${waiting}.`
                : 'По маршруту ещё нет обработанных видео.'
          }
        />
      </>
    )
  }

  return (
    <>
      {heading}
      <MetricsPanel aggregate={aggregate} onAggregateChange={onAggregateChange}>
        <Metric
          label="Заметность за видео"
          value={formatStat(totals.visibility_per_shooting, aggregate)}
        />
        <Metric
          label="Объектов за видео"
          value={formatStat(totals.objects_per_shooting, aggregate)}
        />
        <Metric
          label="Собрано из"
          value={`${pluralAssignments(assignments_total)} · ${pluralShootings(
            totals.shootings_completed,
          )}`}
        />
        <Metric label="Отснято" value={formatDuration(totals.duration_sec)} />
      </MetricsPanel>

      {waiting > 0 && (
        <p className="assignment-pending-note">
          Считаем по {totals.shootings_completed} готовым видео. Ещё {waiting} в
          работе — цифры изменятся после обработки.
        </p>
      )}

      <RouteShootingsChart shootings={shootings} />

      <section className="panel objects-panel">
        <header>
          <h2>Видео маршрута</h2>
          <p>
            Каждое видео отдельно, по дате записи. Разброс в цифрах выше — это
            разброс между этими строками.
          </p>
        </header>
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Когда снимали</th>
                <th>Задание</th>
                <th>Файл</th>
                <th className="numeric">Длительность</th>
                <th className="numeric">Объектов</th>
                <th className="numeric">Заметность</th>
              </tr>
            </thead>
            <tbody>
              {shootings.map((item) => (
                <tr
                  key={item.run_id}
                  className="is-clickable"
                  onClick={() => navigate(`/videos/${item.run_id}`)}
                >
                  <td>{formatDateTime(item.shot_started_at)}</td>
                  <td>{item.assignment.title}</td>
                  <td>{item.source_name}</td>
                  <td className="numeric">{formatDuration(item.duration_sec)}</td>
                  <td className="numeric">{item.objects_count}</td>
                  <td className="numeric">
                    {formatNumber(Number(item.visibility_index.toFixed(1)))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <RollupCharts brands={brands} shootings={shootings} aggregate={aggregate} />
    </>
  )
}
