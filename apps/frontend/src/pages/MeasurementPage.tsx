import { useEffect, useState } from 'react'
import { getMeasurementRuns, getMeasurementSummary } from '../api'
import { RunCharts } from '../components/RunCharts'
import { EmptyState, ErrorBanner } from '../components/common/Feedback'
import { Metric } from '../components/common/Metric'
import { PageHeader } from '../components/common/PageHeader'
import { RunCard } from '../components/common/RunCard'
import { RunsSkeleton } from '../components/common/Skeletons'
import { navigate, uploadPath } from '../routing'
import type { MeasurementSummary, PipelineRun } from '../types'
import { formatDuration, formatNumber, pluralPasses } from '../utils/formatters'

export function MeasurementPage({ measurementId }: { measurementId: string }) {
  const [summary, setSummary] = useState<MeasurementSummary | null>(null)
  const [runs, setRuns] = useState<PipelineRun[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let disposed = false
    const load = () => {
      Promise.all([getMeasurementSummary(measurementId), getMeasurementRuns(measurementId)])
        .then(([summaryValue, runsValue]) => {
          if (disposed) return
          setSummary(summaryValue)
          setRuns(runsValue)
        })
        .catch((reason) => {
          if (!disposed) setError(String(reason))
        })
        .finally(() => {
          if (!disposed) setLoading(false)
        })
    }
    load()
    // Метрики считаются на лету и растут по мере обработки проездов.
    const interval = window.setInterval(load, 5000)
    return () => {
      disposed = true
      window.clearInterval(interval)
    }
  }, [measurementId])

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
        <PageHeader eyebrow="Архив" title="Замер не найден" />
        <ErrorBanner text={error} />
      </div>
    )
  }

  if (!summary) return null

  const { measurement, totals, brands } = summary
  const pending = totals.video_count - totals.completed_count
  const color = measurement.route.color_hex ?? undefined

  return (
    <div className="page">
      <PageHeader
        eyebrow={`${measurement.city.name} · ${measurement.route.name}`}
        title={measurement.title}
        description={`${pluralPasses(totals.video_count)} · ${formatDuration(
          totals.duration_sec,
        )} · обработано ${totals.completed_count} из ${totals.video_count}`}
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
        <span className="measurement-dot" style={color ? { background: color } : undefined} />
        <span>{measurement.route.name}</span>
      </div>

      {error && <ErrorBanner text={error} />}

      <div className="summary-grid">
        <Metric label="Объектов" value={totals.total_objects || '—'} />
        <Metric
          label="Индекс заметности"
          value={totals.visibility_index ? formatNumber(totals.visibility_index) : '—'}
        />
        <Metric label="Проездов" value={totals.video_count} />
        <Metric label="Длительность" value={formatDuration(totals.duration_sec)} />
      </div>

      {totals.completed_count === 0 ? (
        <EmptyState
          text={
            pending > 0
              ? `Метрики замера появятся, когда обработается первое видео. Сейчас в работе ${pending}.`
              : 'В замере пока нет видео.'
          }
        />
      ) : (
        <>
          {pending > 0 && (
            <p className="measurement-pending-note">
              Метрики считаются по {totals.completed_count} готовым проездам. Ещё{' '}
              {pending} в работе — цифры дорастут.
            </p>
          )}
          <RunCharts brands={brands} />
        </>
      )}

      <section className="panel objects-panel">
        <header>
          <h2>Проезды</h2>
          <p>Каждое видео — отдельный проезд маршрута. Откройте, чтобы увидеть разбор.</p>
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
