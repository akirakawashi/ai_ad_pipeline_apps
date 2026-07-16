import { useEffect, useState } from 'react'
import { getCities, getCity, listRuns } from '../api'
import { EmptyState, ErrorBanner } from '../components/common/Feedback'
import { PageHeader } from '../components/common/PageHeader'
import { RunCard } from '../components/common/RunCard'
import { Select } from '../components/common/Select'
import { RunsSkeleton } from '../components/common/Skeletons'
import { Tabs } from '../components/common/Tabs'
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
        measurementId: filters.measurementId,
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
  }, [filters.assigned, filters.measurementId, filters.cityId, filters.routeId, filters.status])

  const update = (changes: Partial<VideoFilters>) => {
    navigate(videosPath({ ...filters, ...changes }))
  }

  const viewMode =
    filters.assigned === false ? 'unassigned' : filters.assigned === true ? 'assigned' : 'all'
  const unassignedOnly = viewMode === 'unassigned'

  const pageTitle =
    viewMode === 'unassigned'
      ? 'Видео без маршрута'
      : viewMode === 'assigned'
        ? 'Видео маршрутов'
        : 'Все видео'

  return (
    <div className="page">
      <PageHeader
        eyebrow="Архив"
        title={pageTitle}
        actions={
          <button className="primary" onClick={() => navigate(uploadPath())}>
            Загрузить видео
          </button>
        }
      />

      <Tabs
        ariaLabel="Какие видео показать"
        value={viewMode}
        options={[
          { value: 'all', label: 'Все видео' },
          { value: 'assigned', label: 'С маршрутом' },
          { value: 'unassigned', label: 'Без маршрута' },
        ]}
        onChange={(tab) =>
          update({
            assigned: tab === 'unassigned' ? false : tab === 'assigned' ? true : undefined,
            ...(tab === 'unassigned'
              ? { cityId: undefined, routeId: undefined, measurementId: undefined }
              : {}),
          })
        }
      />

      <section className="filter-bar">
        {!unassignedOnly && (
          <>
            <div className="field">
              Город
              <Select
                ariaLabel="Город"
                value={filters.cityId ?? ''}
                placeholder="Все города"
                options={[
                  { value: '', label: 'Все города' },
                  ...cities.map((city) => ({ value: city.id, label: city.name })),
                ]}
                onChange={(cityId) =>
                  update({ cityId: cityId || undefined, routeId: undefined })
                }
              />
            </div>
            <div className="field">
              Маршрут
              <Select
                ariaLabel="Маршрут"
                value={filters.routeId ?? ''}
                disabled={!filters.cityId}
                placeholder="Все маршруты"
                options={[
                  { value: '', label: 'Все маршруты' },
                  ...activeRoutes.map((route) => ({ value: route.id, label: route.name })),
                ]}
                onChange={(routeId) => update({ routeId: routeId || undefined })}
              />
            </div>
          </>
        )}
        <div className="field">
          Статус
          <Select
            ariaLabel="Статус"
            value={filters.status ?? ''}
            placeholder="Любой"
            options={[
              { value: '', label: 'Любой' },
              ...STATUS_OPTIONS,
            ]}
            onChange={(status) => update({ status: status || undefined })}
          />
        </div>
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
