import { useEffect, useState } from 'react'
import { getBatchRuns, getBatchSummary } from '../api'
import { RunCharts } from '../components/RunCharts'
import { EmptyState, ErrorBanner } from '../components/common/Feedback'
import { Metric } from '../components/common/Metric'
import { PageHeader } from '../components/common/PageHeader'
import { RunCard } from '../components/common/RunCard'
import { RunsSkeleton } from '../components/common/Skeletons'
import { navigate, uploadPath } from '../routing'
import type { BatchSummary, PipelineRun } from '../types'
import { formatDuration, formatNumber } from '../utils/formatters'

export function BatchPage({ batchId }: { batchId: string }) {
  const [summary, setSummary] = useState<BatchSummary | null>(null)
  const [runs, setRuns] = useState<PipelineRun[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let disposed = false
    const load = () => {
      Promise.all([getBatchSummary(batchId), getBatchRuns(batchId)])
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
  }, [batchId])

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
        <PageHeader eyebrow="Архив" title="Пачка не найдена" />
        <ErrorBanner text={error} />
      </div>
    )
  }

  if (!summary) return null

  const { batch, totals, brands } = summary
  const pending = totals.video_count - totals.completed_count
  const color = batch.route.color_hex ?? undefined

  return (
    <div className="page">
      <PageHeader
        eyebrow={`${batch.city.name} · ${batch.route.name}`}
        title={batch.title}
        description={`${totals.video_count} проездов · ${formatDuration(
          totals.duration_sec,
        )} · обработано ${totals.completed_count} из ${totals.video_count}`}
        actions={
          <div className="page-actions">
            <button
              className="secondary"
              onClick={() =>
                navigate(`/archive/${batch.city.slug}/${batch.route.slug}`)
              }
            >
              К маршруту
            </button>
            <button
              className="primary"
              onClick={() => navigate(uploadPath({ batchId: batch.id }))}
            >
              Добавить видео
            </button>
          </div>
        }
      />

      <div className="batch-heading">
        <span className="batch-dot" style={color ? { background: color } : undefined} />
        <span>{batch.route.name}</span>
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
              ? `Метрики по пачке появятся, когда обработается первое видео. Сейчас в работе ${pending}.`
              : 'В пачке пока нет видео.'
          }
        />
      ) : (
        <>
          {pending > 0 && (
            <p className="batch-pending-note">
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
          <EmptyState text="В пачке нет видео." />
        )}
      </section>
    </div>
  )
}
