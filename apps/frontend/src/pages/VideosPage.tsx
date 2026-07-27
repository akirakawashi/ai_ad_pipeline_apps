import { useEffect, useState } from 'react'
import { getCities, getCity, getRouteAssignments, listRuns } from '../api'
import { EmptyState, ErrorBanner } from '../components/common/Feedback'
import { PageHeader } from '../components/common/PageHeader'
import { RunCard } from '../components/common/RunCard'
import { Select } from '../components/common/Select'
import { RunsSkeleton } from '../components/common/Skeletons'
import { Tabs } from '../components/common/Tabs'
import { navigate, uploadPath, videosPath, type VideoFilters } from '../routing'
import type { City, PipelineRun, Route, Assignment } from '../types'
import type { GeoFeatureCollection } from '../components/RouteMap'

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
  const [assignments, setAssignments] = useState<{
    routeId: string
    items: Assignment[]
  } | null>(null)
  const [routePreviews, setRoutePreviews] = useState<Record<string, GeoFeatureCollection>>({})
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
  const selectedCity = cities.find((city) => city.id === filters.cityId)
  const selectedRoute = activeRoutes.find((route) => route.id === filters.routeId)

  useEffect(() => {
    if (!selectedCity || !selectedRoute) return

    let disposed = false
    getRouteAssignments(selectedCity.slug, selectedRoute.slug)
      .then((page) => {
        if (!disposed) {
          setAssignments({ routeId: selectedRoute.id, items: page.items })
        }
      })
      .catch(() => {
        if (!disposed) setAssignments(null)
      })

    return () => {
      disposed = true
    }
  }, [selectedCity, selectedRoute])

  const activeAssignments =
    assignments && assignments.routeId === filters.routeId ? assignments.items : []

  useEffect(() => {
    let disposed = false
    const load = () => {
      listRuns({
        cityId: filters.cityId,
        routeId: filters.routeId,
        assignmentId: filters.assignmentId,
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
  }, [filters.assigned, filters.assignmentId, filters.cityId, filters.routeId, filters.status])

  useEffect(() => {
    const targets = new Map<string, { routeId: string; citySlug: string }>()
    runs.forEach((run) => {
      if (!run.assignment || routePreviews[run.assignment.route.id]) return
      targets.set(run.assignment.route.id, {
        routeId: run.assignment.route.id,
        citySlug: run.assignment.city.slug,
      })
    })
    const missing = [...targets.values()]
    if (!missing.length) return

    let disposed = false
    const loadPreviews = async () => {
      const citySlugs = [...new Set(missing.map((target) => target.citySlug))]
      const cityDetails = new Map(
        await Promise.all(
          citySlugs.map(async (slug) => [slug, await getCity(slug)] as const),
        ),
      )
      const sources = missing.flatMap(({ routeId, citySlug }) => {
        const route = cityDetails.get(citySlug)?.routes.find((item) => item.id === routeId)
        return route ? ([[routeId, route.geojson_path]] as const) : []
      })
      const previews = await Promise.all(
        sources.map(async ([routeId, path]) => {
          const response = await fetch(`/${path}`)
          if (!response.ok) return null
          return [routeId, (await response.json()) as GeoFeatureCollection] as const
        }),
      )
      if (disposed) return
      const loaded = previews.filter(
        (preview): preview is readonly [string, GeoFeatureCollection] => preview !== null,
      )
      if (loaded.length) {
        setRoutePreviews((current) => ({ ...current, ...Object.fromEntries(loaded) }))
      }
    }
    void loadPreviews().catch(() => undefined)

    return () => {
      disposed = true
    }
  }, [runs, routePreviews])

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
          { value: 'unassigned', label: 'Без задания' },
        ]}
        onChange={(tab) =>
          update({
            assigned: tab === 'unassigned' ? false : tab === 'assigned' ? true : undefined,
            ...(tab === 'unassigned'
              ? { cityId: undefined, routeId: undefined, assignmentId: undefined }
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
                  update({
                    cityId: cityId || undefined,
                    routeId: undefined,
                    assignmentId: undefined,
                  })
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
                onChange={(routeId) =>
                  update({ routeId: routeId || undefined, assignmentId: undefined })
                }
              />
            </div>
            <div className="field">
              Задание
              <Select
                ariaLabel="Задание"
                value={filters.assignmentId ?? ''}
                disabled={!selectedRoute}
                placeholder={
                  !selectedRoute
                    ? 'Сначала выберите маршрут'
                    : 'Все задания'
                }
                options={[
                  { value: '', label: 'Все задания' },
                  ...activeAssignments.map((assignment) => ({
                    value: assignment.id,
                    label: assignment.title,
                  })),
                ]}
                onChange={(assignmentId) =>
                  update({ assignmentId: assignmentId || undefined })
                }
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
          <RunCard
            key={run.run_id}
            run={run}
            showBadges
            routePreview={
              run.assignment ? routePreviews[run.assignment.route.id] : undefined
            }
          />
        ))}
      </div>
    </div>
  )
}
