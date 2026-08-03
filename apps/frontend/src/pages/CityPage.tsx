import { useEffect, useState, type CSSProperties } from 'react'
import {
  getAdStructures,
  getCity,
  getRoadsGeometry,
  getRouteGeometry,
} from '../api'
import { RouteGeozones } from '../components/RouteGeozones'
import { RouteMap, type GeoFeatureCollection } from '../components/RouteMap'
import { EmptyState, ErrorBanner } from '../components/common/Feedback'
import { PageHeader } from '../components/common/PageHeader'
import { RouteMapSkeleton } from '../components/common/Skeletons'
import { navigate } from '../routing'
import type { AdStructure, CityDetail } from '../types'
import { pluralAssignments } from '../utils/formatters'

const FALLBACK_COLOR = '#8a8f98'

/** Заглушка вместо незагруженной геометрии: карта рисует её как «ничего». */
const EMPTY_COLLECTION: GeoFeatureCollection = { type: 'FeatureCollection', features: [] }

export function CityPage({ citySlug }: { citySlug: string }) {
  const [city, setCity] = useState<CityDetail | null>(null)
  const [roads, setRoads] = useState<GeoFeatureCollection | null>(null)
  const [routes, setRoutes] = useState<GeoFeatureCollection[] | null>(null)
  const [structures, setStructures] = useState<AdStructure[]>([])
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

        // Геометрия живёт в базе и приезжает своими запросами: их бэкенд отдаёт
        // с ETag, поэтому повторный заход стоит 304, а не полтора мегабайта.
        // Отсутствие геометрии — законное состояние: город или маршрут можно
        // создать в справочниках, а линию загрузить позже.
        const [roadsData, ...routesData] = await Promise.all([
          detail.has_roads_geometry
            ? getRoadsGeometry(citySlug).catch(() => null)
            : Promise.resolve(null),
          ...detail.routes.map((route) =>
            route.has_geometry
              ? getRouteGeometry(citySlug, route.slug).catch(() => null)
              : Promise.resolve(null),
          ),
        ])
        if (disposed) return
        setRoads((roadsData as GeoFeatureCollection | null) ?? EMPTY_COLLECTION)
        // Порядок сохраняем: карта сопоставляет линии с маршрутами по индексу.
        setRoutes(
          routesData.map(
            (item) => (item as GeoFeatureCollection | null) ?? EMPTY_COLLECTION,
          ),
        )
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

    // Каталог грузим отдельно: его может не быть, и это не повод ломать карту.
    getAdStructures(citySlug)
      .then((page) => {
        if (!disposed) setStructures(page.items)
      })
      .catch(() => undefined)

    return () => {
      disposed = true
    }
  }, [citySlug])

  if (notFound) {
    return (
      <div className="page">
        <PageHeader eyebrow="Города" title="Город не найден" />
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
  // Зоны — только для выбранного маршрута, не для подсвеченного мышью: панель с
  // формой не должна перезагружаться и терять набранный текст от движения курсора.
  const selectedMeta = selectedIndex !== null ? routesMeta[selectedIndex] : null

  const handleReset = () => {
    setHoveredIndex(null)
    setSelectedIndex(null)
  }

  return (
    <div className="page">
      <PageHeader
        eyebrow={city?.name ?? 'Города'}
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
            </div>
            <RouteMap
              roads={roads}
              routes={routes}
              structures={structures}
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
                <h2>Выберите маршрут</h2>
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
                    <small>{pluralAssignments(route.assignment_count)}</small>
                  </span>
                  <span className="route-option-arrow" aria-hidden="true">
                    ↗
                  </span>
                </button>
              ))}
            </div>

            <section className="selection-card" aria-live="polite">
              <p className="panel-kicker">Маршрут</p>
              <h3>{focusedMeta ? focusedMeta.name : 'Маршрут не выбран'}</h3>
              <p className="route-description">
                {focusedMeta && selectedIndex === focusedIndex
                  ? 'Маршрут выбран. Нажмите «Открыть маршрут», чтобы увидеть задания.'
                  : focusedMeta
                    ? 'Нажмите «Выбрать маршрут», чтобы продолжить.'
                    : 'Выберите направление в списке или наведите курсор на его линию на карте.'}
              </p>

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

      {/* key по слагу: смена маршрута создаёт панель заново, а не тащит в неё
          черновик формы от предыдущего. */}
      {selectedMeta && (
        <RouteGeozones
          key={selectedMeta.slug}
          citySlug={citySlug}
          routeSlug={selectedMeta.slug}
          routeName={selectedMeta.name}
        />
      )}
    </div>
  )
}
