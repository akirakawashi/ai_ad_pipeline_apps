import { useEffect, useState } from 'react'
import { getCities } from '../api'
import { getCity } from '../api'
import { CityRoutePreview } from '../components/CityRoutePreview'
import { EmptyState, ErrorBanner } from '../components/common/Feedback'
import { PageHeader } from '../components/common/PageHeader'
import { RunsSkeleton } from '../components/common/Skeletons'
import { navigate, uploadPath } from '../routing'
import type { City } from '../types'
import type { GeoFeatureCollection } from '../components/RouteMap'
import { pluralRoutes } from '../utils/formatters'

export function CitiesPage() {
  const [cities, setCities] = useState<City[]>([])
  const [routePreviews, setRoutePreviews] = useState<Record<string, GeoFeatureCollection[]>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let disposed = false
    getCities()
      .then((result) => {
        if (!disposed) setCities(result)
      })
      .catch((reason) => {
        if (!disposed) setError(String(reason))
      })
      .finally(() => {
        if (!disposed) setLoading(false)
      })
    return () => {
      disposed = true
    }
  }, [])

  useEffect(() => {
    if (!cities.length) return

    let disposed = false
    void Promise.all(
      cities.map(async (city) => {
        try {
          const detail = await getCity(city.slug)
          const responses = await Promise.all(
            detail.routes.map((route) => fetch(`/${route.geojson_path}`)),
          )
          if (responses.some((response) => !response.ok)) return [city.id, []] as const
          const routes = (await Promise.all(
            responses.map((response) => response.json()),
          )) as GeoFeatureCollection[]
          return [city.id, routes] as const
        } catch {
          return [city.id, []] as const
        }
      }),
    ).then((previews) => {
      if (!disposed) setRoutePreviews(Object.fromEntries(previews))
    })

    return () => {
      disposed = true
    }
  }, [cities])

  return (
    <div className="page">
      <PageHeader
        eyebrow="Города"
        title="Города и маршруты"
        description="Выберите город, затем маршрут — внутри лежат задания со съёмками."
      />

      {loading && <RunsSkeleton />}
      {error && <ErrorBanner text={error} />}
      {!loading && !error && !cities.length && (
        <EmptyState text="Города пока не заведены." />
      )}

      {!loading && !error && cities.length > 0 && (
        <div className="cities-catalog">
          <div className="cities-grid">
            {cities.map((city, index) => (
              <button
                className="city-card"
                key={city.id}
                onClick={() => navigate(`/archive/${city.slug}`)}
              >
                <div className="city-card-visual" aria-hidden="true">
                  <div className="city-card-grid" />
                  <span className="city-card-index">
                    {String(index + 1).padStart(2, '0')}
                  </span>
                  <CityRoutePreview routes={routePreviews[city.id] ?? null} />
                  <span className="city-card-visual-label">территория</span>
                </div>

                <div className="city-card-copy">
                  <div className="city-card-kicker">
                    <span className="city-card-live-dot" />
                    Доступен
                  </div>
                  <h2>{city.name}</h2>
                  <p>{city.region ?? 'Регион не указан'}</p>
                  <dl className="city-card-metrics">
                    <div>
                      <dt>Маршруты</dt>
                      <dd>{String(city.route_count).padStart(2, '0')}</dd>
                    </div>
                    <div>
                      <dt>Видео</dt>
                      <dd>{String(city.video_count).padStart(2, '0')}</dd>
                    </div>
                  </dl>
                  <span className="city-card-action">
                    {pluralRoutes(city.route_count)}
                    <span aria-hidden="true">→</span>
                  </span>
                </div>
              </button>
            ))}
          </div>

          <section className="unassigned-videos" aria-labelledby="unassigned-title">
            <div>
              <p className="unassigned-videos-kicker">Без задания</p>
              <h2 id="unassigned-title">Загрузить видео без маршрута</h2>
              <p>Разовая загрузка без привязки к городу и маршруту.</p>
            </div>
            <button
              className="unassigned-videos-action"
              onClick={() => navigate(uploadPath())}
            >
              <span className="unassigned-videos-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24" fill="none">
                  <path d="M4 5.5A1.5 1.5 0 0 1 5.5 4h13A1.5 1.5 0 0 1 20 5.5v13a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 18.5v-13Z" />
                  <path d="M9.5 9 15 12l-5.5 3V9Z" />
                </svg>
              </span>
              <span>
                <strong>Загрузить видео</strong>
                <small>Без привязки к маршруту</small>
              </span>
              <span className="unassigned-videos-arrow" aria-hidden="true">→</span>
            </button>
          </section>
        </div>
      )}
    </div>
  )
}
