import { PageHeader } from '../components/common/PageHeader'
import { CITIES } from '../data/cities'
import { navigate } from '../routing'

export function CitiesPage() {
  return (
    <div className="page">
      <PageHeader
        eyebrow="Маршруты"
        title="Выберите город"
        description="Сейчас доступен один город — список будет расти по мере подключения новых маршрутов."
      />

      <div className="runs-grid">
        {CITIES.map((city) => (
          <button
            className="run-card"
            key={city.id}
            onClick={() => navigate(`/routes/${city.id}`)}
          >
            <div className="run-preview">
              <span>⚑</span>
            </div>
            <div className="run-copy">
              <div className="status status-completed">Доступен</div>
              <h3>{city.name}</h3>
              <p>{city.region}</p>
              <div className="run-meta">
                <span>{city.routeCount} маршрута</span>
              </div>
            </div>
          </button>
        ))}
      </div>
    </div>
  )
}
