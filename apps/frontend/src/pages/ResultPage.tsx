import { useEffect, useMemo, useState } from 'react'
import {
  getRunObjects,
  getRunOverlay,
  getRunPlayback,
  getRunSummary,
  getRunTimeline,
} from '../api'
import { RouteGeozones } from '../components/RouteGeozones'
import { RunCharts } from '../components/RunCharts'
import { ShootingFacts } from '../components/ShootingFacts'
import { VideoOverlayPlayer } from '../components/VideoOverlayPlayer'
import { EmptyState, ErrorBanner } from '../components/common/Feedback'
import { Metric } from '../components/common/Metric'
import { PageHeader } from '../components/common/PageHeader'
import {
  ChartsSkeleton,
  MetricSkeletonGrid,
  ObjectsSkeleton,
  PlayerSkeleton,
} from '../components/common/Skeletons'
import { navigate } from '../routing'
import type {
  OverlayPayload,
  PipelineRun,
  Playback,
  RunObjects,
  RunSummary,
  RunTimeline,
} from '../types'
import { formatDuration, formatNumber } from '../utils/formatters'

export function ResultPage({
  run,
  initialSeek,
  onRunUpdated,
}: {
  run: PipelineRun
  /** Приходит из ?t= — переход с топа объектов задания на нужный кадр. */
  initialSeek?: number
  onRunUpdated: (run: PipelineRun) => void
}) {
  const [summary, setSummary] = useState<RunSummary | null>(null)
  const [objects, setObjects] = useState<RunObjects | null>(null)
  const [timeline, setTimeline] = useState<RunTimeline | null>(null)
  const [playback, setPlayback] = useState<Playback | null>(null)
  const [overlay, setOverlay] = useState<OverlayPayload | null>(null)
  const [seek, setSeek] = useState<number | null>(initialSeek ?? null)
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    void Promise.all([
      getRunSummary(run.run_id),
      getRunObjects(run.run_id),
      getRunTimeline(run.run_id),
      getRunPlayback(run.run_id),
      getRunOverlay(run.run_id),
    ])
      .then(
        ([
          summaryValue,
          objectsValue,
          timelineValue,
          playbackValue,
          overlayValue,
        ]) => {
          setSummary(summaryValue)
          setObjects(objectsValue)
          setTimeline(timelineValue)
          setPlayback(playbackValue)
          setOverlay(overlayValue)
        },
      )
      .catch((reason) =>
        setError(reason instanceof Error ? reason.message : String(reason)),
      )
  }, [run.run_id])

  const topObjects = useMemo(() => objects?.objects.slice(0, 12) ?? [], [objects])

  const copyResultLink = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1600)
    } catch {
      setError('Не удалось скопировать ссылку')
    }
  }

  return (
    <div className="page">
      <PageHeader
        eyebrow={
          run.assignment
            ? `${run.assignment.city.name} · ${run.assignment.route.name} · ${run.assignment.title}`
            : 'Результат анализа'
        }
        title={run.source_name}
        description={`${formatDuration(run.duration_sec)} · ${run.width ?? 0}×${run.height ?? 0}`}
        actions={
          <div className="page-actions">
            {run.assignment && (
              <button
                className="secondary"
                onClick={() => navigate(`/assignments/${run.assignment!.assignment_id}`)}
              >
                К заданию
              </button>
            )}
            <button className="secondary" onClick={() => navigate('/videos')}>
              Все видео
            </button>
            <button className="secondary" onClick={() => void copyResultLink()}>
              {copied ? 'Скопировано' : 'Копировать ссылку'}
            </button>
            <button className="primary" onClick={() => navigate('/upload')}>
              Добавить видео
            </button>
          </div>
        }
      />

      <ShootingFacts run={run} onUpdated={onRunUpdated} />

      {summary ? (
        <div className="summary-grid">
          <Metric label="Объектов" value={summary.totals.total_objects ?? '—'} />
          <Metric
            label="Индекс заметности"
            value={formatNumber(summary.totals.visibility_index)}
          />
          <Metric label="Частота кадров" value={run.fps?.toFixed(1) ?? '—'} />
          <Metric label="Кадров в видео" value={run.frame_count ?? '—'} />
        </div>
      ) : (
        <MetricSkeletonGrid />
      )}

      {error && <ErrorBanner text={error} />}

      {playback?.source_url && overlay ? (
        <section className="panel player-panel">
          <VideoOverlayPlayer
            sourceUrl={playback.source_url}
            overlay={overlay}
            seekRequest={seek}
          />
        </section>
      ) : (
        <PlayerSkeleton />
      )}

      {run.assignment && (
        <RouteGeozones
          citySlug={run.assignment.city.slug}
          routeSlug={run.assignment.route.slug}
          routeName={run.assignment.route.name}
          sourceUrl={playback?.source_url ?? undefined}
        />
      )}

      {summary && timeline && (
        <RunCharts
          brands={summary.brands}
          objects={objects?.objects ?? []}
          timeline={timeline}
          onSeek={setSeek}
        />
      )}
      {(!summary || !timeline) && <ChartsSkeleton />}

      {objects ? (
        <section className="panel objects-panel">
          <header>
            <h2>Самые заметные объекты</h2>
            <p>Нажмите на карточку, чтобы перейти к лучшему кадру.</p>
          </header>
          {topObjects.length ? (
            <div className="objects-grid">
              {topObjects.map((object) => (
                <button
                  key={`${object.object_id}-${object.track_id}`}
                  className="object-card"
                  onClick={() => setSeek(object.best_timestamp_sec)}
                >
                  {object.crop_url ? (
                    <img src={object.crop_url} alt={object.business_brand} />
                  ) : (
                    <div className="crop-placeholder">Кадр</div>
                  )}
                  <strong>{object.business_brand.toUpperCase()}</strong>
                  <span>
                    {Math.round(object.final_brand_conf * 100)}% ·{' '}
                    {object.best_timestamp_sec.toFixed(1)}s
                  </span>
                </button>
              ))}
            </div>
          ) : (
            <EmptyState text="Заметные объекты не найдены." />
          )}
        </section>
      ) : (
        <ObjectsSkeleton />
      )}
    </div>
  )
}
