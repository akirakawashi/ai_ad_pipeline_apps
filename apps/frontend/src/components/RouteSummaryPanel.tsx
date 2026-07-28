import { useState } from 'react'
import { Metric } from './common/Metric'
import { AggregateToggle } from './common/AggregateToggle'
import { EmptyState } from './common/Feedback'
import { RollupCharts } from './RollupCharts'
import { RouteShootingsChart } from './RouteShootingsChart'
import { navigate } from '../routing'
import type { Aggregate, RouteSummary } from '../types'
import {
  formatDateTime,
  formatDuration,
  formatNumber,
  formatStat,
  pluralAssignments,
  pluralShootings,
} from '../utils/formatters'

/**
 * Метрики маршрута. Считаются из съёмок напрямую, поэтому и показываем съёмки:
 * средняя цифра без списка, из чего она собрана, врёт по умолчанию — задание из
 * одного проезда выглядит в ней так же уверенно, как задание из двадцати.
 */
export function RouteSummaryPanel({ summary }: { summary: RouteSummary }) {
  const { totals, brands, shootings, assignments_total } = summary
  const waiting = totals.shootings_total - totals.shootings_completed
  // Среднее по умолчанию: оно слышит каждый проезд. Медиана — чтобы посмотреть
  // на те же съёмки без влияния выбившегося проезда.
  const [aggregate, setAggregate] = useState<Aggregate>('mean')

  if (totals.shootings_completed === 0) {
    return (
      <EmptyState
        text={
          waiting > 0
            ? `Метрики маршрута появятся, когда обработается первая съёмка. Сейчас в работе ${waiting}.`
            : 'По маршруту ещё нет обработанных съёмок.'
        }
      />
    )
  }

  return (
    <>
      <section className="charts-toolbar" aria-label="Как считать показатели">
        <span>Показатели за съёмку</span>
        <AggregateToggle value={aggregate} onChange={setAggregate} />
      </section>

      <div className="summary-grid">
        <Metric
          label="Заметность за съёмку"
          value={formatStat(totals.visibility_per_shooting, aggregate)}
        />
        <Metric
          label="Объектов за съёмку"
          value={formatStat(totals.objects_per_shooting, aggregate)}
        />
        <Metric
          label="Собрано из"
          value={`${pluralAssignments(assignments_total)} · ${pluralShootings(
            totals.shootings_completed,
          )}`}
        />
        <Metric label="Отснято" value={formatDuration(totals.duration_sec)} />
      </div>

      {waiting > 0 && (
        <p className="assignment-pending-note">
          Считаем по {totals.shootings_completed} готовым съёмкам. Ещё {waiting} в
          работе — цифры изменятся после обработки.
        </p>
      )}

      <RouteShootingsChart shootings={shootings} />

      <section className="panel objects-panel">
        <header>
          <h2>Съёмки маршрута</h2>
          <p>
            Каждое видео отдельно, по порядку съёмки. Разброс в цифрах выше — это
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
