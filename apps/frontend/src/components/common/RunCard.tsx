import { CityRoutePreview } from '../CityRoutePreview'
import { statusLabel } from '../../pipeline'
import { navigate } from '../../routing'
import type { PipelineRun } from '../../types'
import { formatDuration } from '../../utils/formatters'
import type { GeoFeatureCollection } from '../RouteMap'

interface RunCardProps {
  run: PipelineRun
  /** Показывать город и маршрут. На странице задания они очевидны из контекста. */
  showBadges?: boolean
  /** Реальная геометрия маршрута для превью в общем архиве. */
  routePreview?: GeoFeatureCollection
}

/**
 * Карточка видео. Общая для «Все видео» и страницы задания — если у одной из
 * них заведётся своя вёрстка, дублирование вернётся туда, откуда его убрали.
 */
export function RunCard({ run, showBadges = false, routePreview }: RunCardProps) {
  const createdAt = new Date(run.created_at)
  const date = createdAt.toLocaleDateString('ru-RU')
  const time = createdAt.toLocaleTimeString('ru-RU', {
    hour: '2-digit',
    minute: '2-digit',
  })

  if (showBadges) {
    const routeText = run.assignment
      ? `${run.assignment.city.name} · ${run.assignment.route.name}`
      : 'Разовая загрузка без маршрута'
    const footerText = run.assignment
      ? `${run.assignment.title} · ${date}`
      : `Без задания · ${date}`

    return (
      <button
        className="run-card archive-run-card"
        onClick={() => navigate(`/videos/${run.run_id}`)}
      >
        <div className="archive-run-visual" aria-hidden="true">
          <span className="archive-run-time">{time}</span>
          <span className="archive-run-visual-label">видео</span>
          {routePreview && (
            <CityRoutePreview routes={[routePreview]} className="archive-run-route-preview" />
          )}
          <span className="archive-run-play">
            {run.status === 'completed' ? '▶' : '···'}
          </span>
        </div>

        <div className="archive-run-copy">
          <div className={`archive-run-kicker status-${run.status}`}>
            <span className="archive-run-live-dot" />
            {statusLabel(run.status)}
          </div>
          <h3>{run.source_name}</h3>
          <p className="archive-run-route">
            {run.assignment?.route.color_hex && (
              <span
                className="archive-run-route-dot"
                style={{ background: run.assignment.route.color_hex }}
              />
            )}
            {routeText}
          </p>
          <dl className="archive-run-metrics">
            <div>
              <dt>Длительность</dt>
              <dd>{formatDuration(run.duration_sec)}</dd>
            </div>
            <div>
              <dt>Готовность</dt>
              <dd>{run.progress}%</dd>
            </div>
          </dl>
          <div className="archive-run-footer">
            <span>{footerText}</span>
            <strong>
              Открыть <span aria-hidden="true">→</span>
            </strong>
          </div>
        </div>
      </button>
    )
  }

  return (
    <button className="run-card" onClick={() => navigate(`/videos/${run.run_id}`)}>
      <div className="run-preview">
        <span>{run.status === 'completed' ? '▶' : '···'}</span>
      </div>
      <div className="run-copy">
        <div className={`status status-${run.status}`}>{statusLabel(run.status)}</div>
        <h3>{run.source_name}</h3>
        {showBadges && (
          <div className="run-badges">
            {run.assignment ? (
              <>
                <span
                  className="run-badge"
                  style={
                    run.assignment.route.color_hex
                      ? {
                          background: `color-mix(in srgb, ${run.assignment.route.color_hex} 16%, transparent)`,
                          borderColor: `color-mix(in srgb, ${run.assignment.route.color_hex} 45%, transparent)`,
                          color: run.assignment.route.color_hex,
                        }
                      : undefined
                  }
                >
                  {run.assignment.city.name} · {run.assignment.route.name}
                </span>
                <span className="run-badge muted">{run.assignment.title}</span>
              </>
            ) : (
              <span className="run-badge muted">Без задания</span>
            )}
          </div>
        )}
        <p>{createdAt.toLocaleString('ru-RU')}</p>
        <div className="run-meta">
          <span>{formatDuration(run.duration_sec)}</span>
          <span>{run.progress}%</span>
        </div>
      </div>
    </button>
  )
}
