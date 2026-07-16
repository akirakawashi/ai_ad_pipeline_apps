import { useEffect, useState } from 'react'
import { getCities } from '../api'
import { EmptyState, ErrorBanner } from '../components/common/Feedback'
import { PageHeader } from '../components/common/PageHeader'
import { RunsSkeleton } from '../components/common/Skeletons'
import { navigate, videosPath } from '../routing'
import type { City } from '../types'

function pluralRoutes(count: number): string {
  const mod10 = count % 10
  const mod100 = count % 100
  if (mod10 === 1 && mod100 !== 11) return `${count} маршрут`
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) {
    return `${count} маршрута`
  }
  return `${count} маршрутов`
}

export function CitiesPage() {
  const [cities, setCities] = useState<City[]>([])
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

  return (
    <div className="page">
      <PageHeader
        eyebrow="Архив"
        title="Города и маршруты"
        description="Выберите город, затем маршрут — внутри лежат пачки видео."
      />

      {loading && <RunsSkeleton />}
      {error && <ErrorBanner text={error} />}
      {!loading && !error && !cities.length && (
        <EmptyState text="Города пока не заведены." />
      )}

      {!loading && (
        <div className="runs-grid">
          {cities.map((city) => (
            <button
              className="run-card"
              key={city.id}
              onClick={() => navigate(`/archive/${city.slug}`)}
            >
              <div className="run-preview">
                <span>⚑</span>
              </div>
              <div className="run-copy">
                <div className="status status-completed">Доступен</div>
                <h3>{city.name}</h3>
                <p>{city.region}</p>
                <div className="run-meta">
                  <span>{pluralRoutes(city.route_count)}</span>
                  <span>{city.video_count} видео</span>
                </div>
              </div>
            </button>
          ))}

          <button
            className="run-card unassigned-card"
            onClick={() => navigate(videosPath({ assigned: false }))}
          >
            <div className="run-preview">
              <span>▦</span>
            </div>
            <div className="run-copy">
              <div className="status status-queued">Вне маршрутов</div>
              <h3>Без маршрута</h3>
              <p>Разовые и тестовые загрузки</p>
            </div>
          </button>
        </div>
      )}
    </div>
  )
}
