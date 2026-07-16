import { useEffect, useState } from 'react'
import { getMeasurementRuns, getMeasurementSummary } from '../api'
import { MeasurementCharts } from '../components/MeasurementCharts'
import { EmptyState, ErrorBanner } from '../components/common/Feedback'
import { Metric } from '../components/common/Metric'
import { PageHeader } from '../components/common/PageHeader'
import { RunCard } from '../components/common/RunCard'
import { RunsSkeleton } from '../components/common/Skeletons'
import { navigate, uploadPath } from '../routing'
import type { MeasurementStat, MeasurementSummary, PipelineRun } from '../types'
import { formatDuration, formatNumber, pluralPasses } from '../utils/formatters'

/** Обработка идёт минутами — чаще смотреть незачем. */
const POLL_INTERVAL_MS = 20000

function stat(value: MeasurementStat, digits = 1): string {
  if (!value.mean) return '—'
  const mean = formatNumber(Number(value.mean.toFixed(digits)))
  if (!value.std) return mean
  return `${mean} ± ${value.std.toFixed(digits)}`
}

export function MeasurementPage({ measurementId }: { measurementId: string }) {
  const [summary, setSummary] = useState<MeasurementSummary | null>(null)
  const [runs, setRuns] = useState<PipelineRun[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  // Пока есть необработанные проезды — опрашиваем. Все готовы — таймер снимаем,
  // иначе открытая вкладка вечно тянет CSV каждого проезда из хранилища.
  const [pending, setPending] = useState(true)

  useEffect(() => {
    let disposed = false
    const load = () => {
      Promise.all([
        getMeasurementSummary(measurementId),
        getMeasurementRuns(measurementId),
      ])
        .then(([summaryValue, runsValue]) => {
          if (disposed) return
          setSummary(summaryValue)
          setRuns(runsValue)
          setPending(
            summaryValue.totals.passes_completed < summaryValue.totals.passes_total,
          )
        })
        .catch((reason) => {
          if (!disposed) setError(String(reason))
        })
        .finally(() => {
          if (!disposed) setLoading(false)
        })
    }
    load()
    if (!pending) {
      return () => {
        disposed = true
      }
    }
    const interval = window.setInterval(load, POLL_INTERVAL_MS)
    return () => {
      disposed = true
      window.clearInterval(interval)
    }
  }, [measurementId, pending])

  if (loading && !summary) {
    return (
      <div className="page">
        <RunsSkeleton />
      </div>
    )
  }

  if (error && !summary) {
    return (
      <div className="page">
        <PageHeader eyebrow="Города" title="Замер не найден" />
        <ErrorBanner text={error} />
      </div>
    )
  }

  if (!summary) return null

  const { measurement, totals, brands, passes } = summary
  const waiting = totals.passes_total - totals.passes_completed
  const color = measurement.route.color_hex ?? undefined

  return (
    <div className="page">
      <PageHeader
        eyebrow={`${measurement.city.name} · ${measurement.route.name}`}
        title={measurement.title}
        description={`${pluralPasses(totals.passes_total)} · отснято ${formatDuration(
          totals.duration_sec,
        )} · обработано ${totals.passes_completed} из ${totals.passes_total}`}
        actions={
          <div className="page-actions">
            <button
              className="secondary"
              onClick={() =>
                navigate(`/archive/${measurement.city.slug}/${measurement.route.slug}`)
              }
            >
              К маршруту
            </button>
            <button
              className="primary"
              onClick={() => navigate(uploadPath({ measurementId: measurement.id }))}
            >
              Добавить видео
            </button>
          </div>
        }
      />

      <div className="measurement-heading">
        <span
          className="measurement-dot"
          style={color ? { background: color } : undefined}
        />
        <span>{measurement.route.name}</span>
      </div>

      {error && <ErrorBanner text={error} />}

      <div className="summary-grid">
        <Metric label="Объектов за проезд" value={stat(totals.objects_per_pass)} />
        <Metric
          label="Заметность за проезд"
          value={stat(totals.visibility_per_pass)}
        />
        <Metric label="Проездов" value={totals.passes_total} />
        <Metric label="Отснято" value={formatDuration(totals.duration_sec)} />
      </div>

      {totals.passes_completed === 0 ? (
        <EmptyState
          text={
            waiting > 0
              ? `Метрики появятся, когда обработается первый проезд. Сейчас в работе ${waiting}.`
              : 'В замере пока нет видео.'
          }
        />
      ) : (
        <>
          {waiting > 0 && (
            <p className="measurement-pending-note">
              Считаем по {totals.passes_completed} готовым проездам. Ещё {waiting} в
              работе — цифры дорастут.
            </p>
          )}
          <MeasurementCharts brands={brands} passes={passes} />
        </>
      )}

      <section className="panel objects-panel">
        <header>
          <h2>Проезды</h2>
          <p>
            Каждое видео — отдельный проезд маршрута. Откройте, чтобы увидеть разбор.
          </p>
        </header>
        {runs.length ? (
          <div className="runs-grid">
            {runs.map((run) => (
              <RunCard key={run.run_id} run={run} />
            ))}
          </div>
        ) : (
          <EmptyState text="В замере нет видео." />
        )}
      </section>
    </div>
  )
}
