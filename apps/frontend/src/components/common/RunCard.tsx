import { statusLabel } from '../../pipeline'
import { navigate } from '../../routing'
import type { PipelineRun } from '../../types'
import { formatDuration } from '../../utils/formatters'

interface RunCardProps {
  run: PipelineRun
  /** Показывать город и маршрут. На странице замера они очевидны из контекста. */
  showBadges?: boolean
}

/**
 * Карточка видео. Общая для «Все видео» и страницы замера — если у одной из
 * них заведётся своя вёрстка, дублирование вернётся туда, откуда его убрали.
 */
export function RunCard({ run, showBadges = false }: RunCardProps) {
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
            {run.measurement ? (
              <>
                <span
                  className="run-badge"
                  style={
                    run.measurement.route.color_hex
                      ? {
                          background: `color-mix(in srgb, ${run.measurement.route.color_hex} 16%, transparent)`,
                          borderColor: `color-mix(in srgb, ${run.measurement.route.color_hex} 45%, transparent)`,
                          color: run.measurement.route.color_hex,
                        }
                      : undefined
                  }
                >
                  {run.measurement.city.name} · {run.measurement.route.name}
                </span>
                <span className="run-badge muted">{run.measurement.title}</span>
              </>
            ) : (
              <span className="run-badge muted">Без маршрута</span>
            )}
          </div>
        )}
        <p>{new Date(run.created_at).toLocaleString('ru-RU')}</p>
        <div className="run-meta">
          <span>{formatDuration(run.duration_sec)}</span>
          <span>{run.progress}%</span>
        </div>
      </div>
    </button>
  )
}
