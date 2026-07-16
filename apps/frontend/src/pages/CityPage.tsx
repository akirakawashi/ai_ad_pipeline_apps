import { useEffect, useState, type CSSProperties } from 'react'
import { getCity } from '../api'
import { RouteMap, type GeoFeatureCollection } from '../components/RouteMap'
import { EmptyState, ErrorBanner } from '../components/common/Feedback'
import { PageHeader } from '../components/common/PageHeader'
import { RouteMapSkeleton } from '../components/common/Skeletons'
import { navigate } from '../routing'
import type { CityDetail } from '../types'

const FALLBACK_COLOR = '#8a8f98'

export function CityPage({ citySlug }: { citySlug: string }) {
  const [city, setCity] = useState<CityDetail | null>(null)
  const [roads, setRoads] = useState<GeoFeatureCollection | null>(null)
  const [routes, setRoutes] = useState<GeoFeatureCollection[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [notFound, setNotFound] = useState(false)
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null)
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null)

  useEffect(() => {
    let disposed = false

    getCity(citySlug)
      .then(async (detail) => {
        if (disposed) return
        setCity(detail)

        // Пути к geojson приходят из БД целиком; фронт добавляет только слэш.
        const responses = await Promise.all([
          fetch(`/${detail.roads_geojson_path ?? ''}`),
          ...detail.routes.map((route) => fetch(`/${route.geojson_path}`)),
        ])
        if (responses.some((response) => !response.ok)) {
          throw new Error('Не удалось загрузить данные маршрутов.')
        }
        const [roadsData, ...routesData] = await Promise.all(
          responses.map((response) => response.json()),
        )
        if (disposed) return
        setRoads(roadsData)
        setRoutes(routesData)
      })
      .catch((reason) => {
        if (disposed) return
        if (String(reason).includes('не найден')) {
          setNotFound(true)
        } else {
          setError(String(reason))
        }
      })
      .finally(() => {
        if (!disposed) setLoading(false)
      })

    return () => {
      disposed = true
    }
  }, [citySlug])

  if (notFound) {
    return (
      <div className="page">
        <PageHeader eyebrow="Архив" title="Город не найден" />
        <EmptyState
          text="Такого города пока нет в списке."
          action={
            <button className="primary" onClick={() => navigate('/archive')}>
              Выбрать город
            </button>
          }
        />
      </div>
    )
  }

  const routesMeta = city?.routes ?? []
  const routeColors = routesMeta.map((route) => route.color_hex ?? FALLBACK_COLOR)
  const focusedIndex = hoveredIndex ?? selectedIndex
  const focusedMeta = focusedIndex !== null ? routesMeta[focusedIndex] : null
  const focusedSegmentCount =
    focusedIndex !== null ? routes?.[focusedIndex]?.features.length : undefined

  const handleReset = () => {
    setHoveredIndex(null)
    setSelectedIndex(null)
  }

  return (
    <div className="page">
      <PageHeader
        eyebrow={city?.name ?? 'Архив'}
        title="Выберите маршрут"
        description="Наведите курсор на линию на карте или выберите направление в списке."
        actions={
          <button
            className="ghost-button"
            onClick={handleReset}
            disabled={focusedIndex === null}
          >
            Сбросить выбор
          </button>
        }
      />

      {error && <ErrorBanner text={error} />}
      {loading && <RouteMapSkeleton />}

      {!loading && city && roads && routes && (
        <div className="content-grid">
          <section className="panel map-card">
            <div className="map-toolbar">
              <span className="city-label">{city.name}</span>
              <span className="map-hint">Интерактивная схема</span>
            </div>
            <RouteMap
              roads={roads}
              routes={routes}
              colors={routeColors}
              routeNames={routesMeta.map((route) => route.name)}
              hoveredIndex={hoveredIndex}
              selectedIndex={selectedIndex}
              onHoverChange={setHoveredIndex}
              onSelect={setSelectedIndex}
            />
          </section>

          <aside className="panel side-panel" aria-label="Выбор маршрута">
            <div className="panel-heading">
              <div>
                <p className="panel-kicker">Направления</p>
                <h2>Куда поедем?</h2>
              </div>
              <span className="route-count">
                {String(routesMeta.length).padStart(2, '0')}
              </span>
            </div>

            <div className="route-options" role="group" aria-label="Доступные маршруты">
              {routesMeta.map((route, index) => (
                <button
                  key={route.id}
                  type="button"
                  className={`route-option${focusedIndex === index ? ' is-active' : ''}${
                    selectedIndex === index ? ' is-selected' : ''
                  }`}
                  style={{ '--route-color': routeColors[index] } as CSSProperties}
                  aria-pressed={selectedIndex === index}
                  onMouseEnter={() => setHoveredIndex(index)}
                  onMouseLeave={() => setHoveredIndex(null)}
                  onFocus={() => setHoveredIndex(index)}
                  onBlur={() => setHoveredIndex(null)}
                  onClick={() => setSelectedIndex(index)}
                >
                  <span className="route-number">
                    {String(index + 1).padStart(2, '0')}
                  </span>
                  <span className="route-option-copy">
                    <strong>{route.name}</strong>
                    <small>
                      {route.color_label} · {route.batch_count} пачек
                    </small>
                  </span>
                  <span className="route-option-arrow" aria-hidden="true">
                    ↗
                  </span>
                </button>
              ))}
            </div>

            <section className="selection-card" aria-live="polite">
              <p className="panel-kicker">Текущий фокус</p>
              <h3>{focusedMeta ? focusedMeta.name : 'Маршрут не выбран'}</h3>
              <p className="route-description">
                {focusedMeta && selectedIndex === focusedIndex
                  ? `Маршрут закреплён. Нажмите «Открыть маршрут», чтобы увидеть пачки. ${focusedMeta.color_label}.`
                  : focusedMeta
                    ? `Наведите курсор на карту или нажмите «Выбрать маршрут», чтобы закрепить его. ${focusedMeta.color_label}.`
                    : 'Выберите направление в списке или наведите курсор на его линию на карте.'}
              </p>

              <div className="stats">
                <div className="stat-card">
                  <span>Сегментов</span>
                  <strong>{focusedSegmentCount ?? '—'}</strong>
                </div>
                <div className="stat-card">
                  <span>Пачек</span>
                  <strong>{focusedMeta ? focusedMeta.batch_count : '—'}</strong>
                </div>
              </div>

              <button
                className="primary action-button"
                type="button"
                disabled={focusedIndex === null}
                onClick={() => {
                  if (focusedIndex === null) return
                  if (selectedIndex === focusedIndex) {
                    navigate(`/archive/${citySlug}/${routesMeta[focusedIndex].slug}`)
                  } else {
                    setSelectedIndex(focusedIndex)
                  }
                }}
              >
                {selectedIndex !== null && focusedIndex === selectedIndex
                  ? 'Открыть маршрут →'
                  : 'Выбрать маршрут'}
              </button>
            </section>
          </aside>
        </div>
      )}
    </div>
  )
}
