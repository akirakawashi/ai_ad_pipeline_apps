import { useEffect, useState } from 'react'
import { getCity, getRouteMeasurements } from '../api'
import { EmptyState, ErrorBanner } from '../components/common/Feedback'
import { PageHeader } from '../components/common/PageHeader'
import { RunsSkeleton } from '../components/common/Skeletons'
import { navigate, uploadPath } from '../routing'
import type { Route, RouteMeasurement } from '../types'
import { pluralMeasurements } from '../utils/formatters'

function measurementProgressLabel(measurement: RouteMeasurement): string {
  const { completed, processing, queued, uploading, processing_failed } =
    measurement.status_counts
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
  const [measurements, setBatches] = useState<RouteMeasurement[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let disposed = false
    const load = () => {
      Promise.all([getCity(citySlug), getRouteMeasurements(citySlug, routeSlug)])
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
    // Замеры показывают статус обработки — он меняется без нашего участия.
    const interval = window.setInterval(load, 5000)
    return () => {
      disposed = true
      window.clearInterval(interval)
    }
  }, [citySlug, routeSlug])

  const totalVideos = measurements.reduce((sum, measurement) => sum + measurement.video_count, 0)

  return (
    <div className="page">
      <PageHeader
        eyebrow={cityName || 'Маршрут'}
        title={route?.name ?? 'Замеры маршрута'}
        description={
          route
            ? `${pluralMeasurements(measurements.length)} · ${totalVideos} видео`
            : undefined
        }
        actions={
          <button
            className="primary"
            onClick={() => navigate(uploadPath({ citySlug, routeSlug }))}
          >
            Новый замер
          </button>
        }
      />

      {error && <ErrorBanner text={error} />}
      {loading && <RunsSkeleton />}

      {!loading && !error && !measurements.length && (
        <EmptyState
          text="На этом маршруте ещё нет замеров. Загрузите первый."
          action={
            <button
              className="primary"
              onClick={() => navigate(uploadPath({ citySlug, routeSlug }))}
            >
              Новый замер
            </button>
          }
        />
      )}

      <div className="runs-grid">
        {measurements.map((measurement) => (
          <button
            className="run-card"
            key={measurement.id}
            onClick={() => navigate(`/measurements/${measurement.id}`)}
          >
            <div
              className="run-preview"
              style={
                measurement.route.color_hex
                  ? { borderColor: measurement.route.color_hex }
                  : undefined
              }
            >
              <span>▦</span>
            </div>
            <div className="run-copy">
              <div className="status status-queued">
                {measurement.video_count} видео
              </div>
              <h3>{measurement.title}</h3>
              <p>{measurementProgressLabel(measurement)}</p>
            </div>
          </button>
        ))}
      </div>
    </div>
  )
}
