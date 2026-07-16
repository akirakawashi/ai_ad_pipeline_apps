import { useEffect, useState } from 'react'
import { getCities, getCity, listRuns } from '../api'
import { EmptyState, ErrorBanner } from '../components/common/Feedback'
import { PageHeader } from '../components/common/PageHeader'
import { RunCard } from '../components/common/RunCard'
import { RunsSkeleton } from '../components/common/Skeletons'
import { navigate, uploadPath, videosPath, type VideoFilters } from '../routing'
import type { City, PipelineRun, Route } from '../types'

const STATUS_OPTIONS: Array<{ value: string; label: string }> = [
  { value: 'uploading', label: 'Загружается' },
  { value: 'queued', label: 'В очереди' },
  { value: 'processing', label: 'Обрабатывается' },
  { value: 'completed', label: 'Готово' },
  { value: 'processing_failed', label: 'Ошибка' },
]

export function VideosPage({ filters }: { filters: VideoFilters }) {
  const [runs, setRuns] = useState<PipelineRun[]>([])
  const [cities, setCities] = useState<City[]>([])
  const [routes, setRoutes] = useState<{ cityId: string; items: Route[] } | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getCities()
      .then(setCities)
      .catch(() => {
        // Фильтры — вспомогательные: без каталога список видео всё равно работает.
      })
  }, [])

  useEffect(() => {
    if (!filters.cityId) return
    const city = cities.find((item) => item.id === filters.cityId)
    if (!city) return
    let disposed = false
    getCity(city.slug)
      .then((detail) => {
        if (!disposed) setRoutes({ cityId: detail.id, items: detail.routes })
      })
      .catch(() => undefined)
    return () => {
      disposed = true
    }
  }, [cities, filters.cityId])

  // Выводим, а не сбрасываем в эффекте: маршруты чужого города показывать нельзя.
  const activeRoutes =
    routes && routes.cityId === filters.cityId ? routes.items : []

  useEffect(() => {
    let disposed = false
    const load = () => {
      listRuns({
        cityId: filters.cityId,
        routeId: filters.routeId,
        batchId: filters.batchId,
        status: filters.status,
        assigned: filters.assigned,
      })
        .then((result) => {
          if (!disposed) setRuns(result.items)
        })
        .catch((reason) => {
          if (!disposed) setError(String(reason))
        })
        .finally(() => {
          if (!disposed) setLoading(false)
        })
    }
    load()
    const interval = window.setInterval(load, 5000)
    return () => {
      disposed = true
      window.clearInterval(interval)
    }
  }, [filters.assigned, filters.batchId, filters.cityId, filters.routeId, filters.status])

  const update = (changes: Partial<VideoFilters>) => {
    navigate(videosPath({ ...filters, ...changes }))
  }

  const unassignedOnly = filters.assigned === false

  return (
    <div className="page">
      <PageHeader
        eyebrow="Архив"
        title={unassignedOnly ? 'Видео без маршрута' : 'Все видео'}
        actions={
          <button className="primary" onClick={() => navigate(uploadPath())}>
            Загрузить видео
          </button>
        }
      />

      <section className="filter-bar">
        <label>
          Город
          <select
            value={filters.cityId ?? ''}
            disabled={unassignedOnly}
            onChange={(event) =>
              update({ cityId: event.target.value || undefined, routeId: undefined })
            }
          >
            <option value="">Все города</option>
            {cities.map((city) => (
              <option key={city.id} value={city.id}>
                {city.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Маршрут
          <select
            value={filters.routeId ?? ''}
            disabled={unassignedOnly || !filters.cityId}
            onChange={(event) => update({ routeId: event.target.value || undefined })}
          >
            <option value="">Все маршруты</option>
            {activeRoutes.map((route) => (
              <option key={route.id} value={route.id}>
                {route.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Статус
          <select
            value={filters.status ?? ''}
            onChange={(event) => update({ status: event.target.value || undefined })}
          >
            <option value="">Любой</option>
            {STATUS_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label className="filter-toggle">
          <input
            type="checkbox"
            checked={unassignedOnly}
            onChange={(event) =>
              update({
                assigned: event.target.checked ? false : undefined,
                cityId: undefined,
                routeId: undefined,
                batchId: undefined,
              })
            }
          />
          Только без маршрута
        </label>
      </section>

      {loading && <RunsSkeleton />}
      {error && <ErrorBanner text={error} />}
      {!loading && !error && !runs.length && (
        <EmptyState
          text="Видео не найдены."
          action={
            <button className="primary" onClick={() => navigate(uploadPath())}>
              Загрузить видео
            </button>
          }
        />
      )}

      <div className="runs-grid">
        {runs.map((run) => (
          <RunCard key={run.run_id} run={run} showBadges />
        ))}
      </div>
    </div>
  )
}
