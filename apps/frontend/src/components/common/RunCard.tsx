import { statusLabel } from '../../pipeline'
import { navigate } from '../../routing'
import type { PipelineRun } from '../../types'
import { formatDuration } from '../../utils/formatters'

interface RunCardProps {
  run: PipelineRun
  /** Показывать город и маршрут. На странице пачки они очевидны из контекста. */
  showBadges?: boolean
}

/**
 * Карточка видео. Общая для «Все видео» и страницы пачки — если у одной из
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
            {run.batch ? (
              <>
                <span
                  className="run-badge"
                  style={
                    run.batch.route.color_hex
                      ? { borderColor: run.batch.route.color_hex }
                      : undefined
                  }
                >
                  {run.batch.city.name} · {run.batch.route.name}
                </span>
                <span className="run-badge muted">{run.batch.title}</span>
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
