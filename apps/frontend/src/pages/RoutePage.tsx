import { useEffect, useState } from 'react'
import { getCity, getRouteBatches } from '../api'
import { EmptyState, ErrorBanner } from '../components/common/Feedback'
import { PageHeader } from '../components/common/PageHeader'
import { RunsSkeleton } from '../components/common/Skeletons'
import { navigate, uploadPath } from '../routing'
import type { Route, RouteBatch } from '../types'

function batchProgressLabel(batch: RouteBatch): string {
  const { completed, processing, queued, uploading, processing_failed } =
    batch.status_counts
  const parts: string[] = []
  if (completed) parts.push(`Готово ${completed}`)
  if (processing + queued + uploading) {
    parts.push(`В работе ${processing + queued + uploading}`)
  }
  if (processing_failed) parts.push(`Ошибок ${processing_failed}`)
  return parts.join(' · ') || 'Пусто'
}

export function RoutePage({
  citySlug,
  routeSlug,
}: {
  citySlug: string
  routeSlug: string
}) {
  const [route, setRoute] = useState<Route | null>(null)
  const [cityName, setCityName] = useState('')
  const [batches, setBatches] = useState<RouteBatch[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let disposed = false
    const load = () => {
      Promise.all([getCity(citySlug), getRouteBatches(citySlug, routeSlug)])
        .then(([city, page]) => {
          if (disposed) return
          setCityName(city.name)
          setRoute(city.routes.find((item) => item.slug === routeSlug) ?? null)
          setBatches(page.items)
        })
        .catch((reason) => {
          if (!disposed) setError(String(reason))
        })
        .finally(() => {
          if (!disposed) setLoading(false)
        })
    }
    load()
    // Пачки показывают статус обработки — он меняется без нашего участия.
    const interval = window.setInterval(load, 5000)
    return () => {
      disposed = true
      window.clearInterval(interval)
    }
  }, [citySlug, routeSlug])

  const totalVideos = batches.reduce((sum, batch) => sum + batch.video_count, 0)

  return (
    <div className="page">
      <PageHeader
        eyebrow={cityName || 'Маршрут'}
        title={route?.name ?? 'Пачки маршрута'}
        description={
          route
            ? `${route.color_label ?? ''} · ${batches.length} пачек · ${totalVideos} видео`
            : undefined
        }
        actions={
          <button
            className="primary"
            onClick={() => navigate(uploadPath({ citySlug, routeSlug }))}
          >
            Загрузить пачку
          </button>
        }
      />

      {error && <ErrorBanner text={error} />}
      {loading && <RunsSkeleton />}

      {!loading && !error && !batches.length && (
        <EmptyState
          text="На этом маршруте ещё нет пачек. Загрузите первую."
          action={
            <button
              className="primary"
              onClick={() => navigate(uploadPath({ citySlug, routeSlug }))}
            >
              Загрузить пачку
            </button>
          }
        />
      )}

      <div className="runs-grid">
        {batches.map((batch) => (
          <button
            className="run-card"
            key={batch.id}
            onClick={() => navigate(`/batches/${batch.id}`)}
          >
            <div
              className="run-preview"
              style={
                batch.route.color_hex
                  ? { borderColor: batch.route.color_hex }
                  : undefined
              }
            >
              <span>▦</span>
            </div>
            <div className="run-copy">
              <div className="status status-queued">
                {batch.video_count} видео
              </div>
              <h3>{batch.title}</h3>
              <p>{batchProgressLabel(batch)}</p>
            </div>
          </button>
        ))}
      </div>
    </div>
  )
}
