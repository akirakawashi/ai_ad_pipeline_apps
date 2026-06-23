import { useEffect, useMemo, useState } from 'react'
import {
  completeUpload,
  createRun,
  getRun,
  getRunObjects,
  getRunOverlay,
  getRunPlayback,
  getRunSummary,
  getRunTimeline,
  listRuns,
  uploadVideo,
} from './api'
import { RunCharts } from './components/RunCharts'
import { VideoOverlayPlayer } from './components/VideoOverlayPlayer'
import type {
  OverlayPayload,
  PipelineRun,
  Playback,
  RunObjects,
  RunSummary,
  RunTimeline,
} from './types'
import './App.css'

type Route =
  | { page: 'runs' }
  | { page: 'new' }
  | { page: 'run'; runId: string }

function currentRoute(): Route {
  const match = window.location.pathname.match(/^\/runs\/([^/]+)$/)
  if (match) return { page: 'run', runId: match[1] }
  if (window.location.pathname === '/runs/new') return { page: 'new' }
  return { page: 'runs' }
}

function navigate(path: string) {
  window.history.pushState({}, '', path)
  window.dispatchEvent(new PopStateEvent('popstate'))
}

function App() {
  const [route, setRoute] = useState<Route>(currentRoute)
  useEffect(() => {
    const update = () => setRoute(currentRoute())
    window.addEventListener('popstate', update)
    return () => window.removeEventListener('popstate', update)
  }, [])

  return (
    <div className="app-shell">
      <header className="topbar">
        <button className="brand" onClick={() => navigate('/runs')}>
          <span className="brand-mark">V</span>
          <span>
            <strong>Volna Vision</strong>
            <small>Outdoor analytics</small>
          </span>
        </button>
        <nav>
          <button onClick={() => navigate('/runs')}>История</button>
          <button className="primary" onClick={() => navigate('/runs/new')}>
            Загрузить видео
          </button>
        </nav>
      </header>
      <main>
        {route.page === 'runs' && <RunsPage />}
        {route.page === 'new' && <UploadPage />}
        {route.page === 'run' && <RunPage runId={route.runId} />}
      </main>
    </div>
  )
}

function RunsPage() {
  const [runs, setRuns] = useState<PipelineRun[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let disposed = false
    const load = () => {
      listRuns()
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
  }, [])

  return (
    <div className="page">
      <PageHeader
        eyebrow="Библиотека"
        title="Обработанные видео"
        description="Все загрузки сохраняются как независимые runs."
      />
      {loading && <EmptyState text="Загрузка истории…" />}
      {error && <ErrorBanner text={error} />}
      {!loading && !runs.length && (
        <EmptyState text="Видео ещё не загружались." />
      )}
      <div className="runs-grid">
        {runs.map((run) => (
          <button
            className="run-card"
            key={run.run_id}
            onClick={() => navigate(`/runs/${run.run_id}`)}
          >
            <div className="run-preview">
              <span>{run.status === 'completed' ? '▶' : '···'}</span>
            </div>
            <div className="run-copy">
              <div className={`status status-${run.status}`}>
                {statusLabel(run.status)}
              </div>
              <h3>{run.source_name}</h3>
              <p>{new Date(run.created_at).toLocaleString('ru-RU')}</p>
              <div className="run-meta">
                <span>{formatDuration(run.duration_sec)}</span>
                <span>{run.progress}%</span>
              </div>
            </div>
          </button>
        ))}
      </div>
    </div>
  )
}

function UploadPage() {
  const [file, setFile] = useState<File | null>(null)
  const [progress, setProgress] = useState(0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const startUpload = async () => {
    if (!file) return
    setBusy(true)
    setError(null)
    try {
      const run = await createRun(file)
      await uploadVideo(run.upload, file, setProgress)
      await completeUpload(run.run_id)
      navigate(`/runs/${run.run_id}`)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
      setBusy(false)
    }
  }

  return (
    <div className="page narrow-page">
      <PageHeader
        eyebrow="Новая обработка"
        title="Загрузите видео маршрута"
        description="После загрузки видео автоматически попадёт в очередь ML pipeline."
      />
      <section
        className="upload-panel"
        onDragOver={(event) => event.preventDefault()}
        onDrop={(event) => {
          event.preventDefault()
          setFile(event.dataTransfer.files[0] ?? null)
        }}
      >
        <div className="upload-icon">↑</div>
        <h2>{file ? file.name : 'Перетащите видео сюда'}</h2>
        <p>
          {file
            ? `${formatBytes(file.size)} · ${file.type || 'video'}`
            : 'MP4, MOV, MKV или WebM'}
        </p>
        <label className="file-button">
          Выбрать файл
          <input
            type="file"
            accept="video/*,.mkv"
            disabled={busy}
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          />
        </label>
        {busy && <ProgressBar progress={progress} label="Загрузка в MinIO" />}
        {error && <ErrorBanner text={error} />}
        <button
          className="primary action-button"
          disabled={!file || busy}
          onClick={() => void startUpload()}
        >
          {busy ? 'Загрузка…' : 'Запустить обработку'}
        </button>
      </section>
    </div>
  )
}

function RunPage({ runId }: { runId: string }) {
  const [run, setRun] = useState<PipelineRun | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let disposed = false
    let timer = 0
    const load = async () => {
      try {
        const value = await getRun(runId)
        if (disposed) return
        setRun(value)
        if (!['completed', 'processing_failed'].includes(value.status)) {
          timer = window.setTimeout(load, 1500)
        }
      } catch (reason) {
        if (!disposed) setError(String(reason))
      }
    }
    void load()
    return () => {
      disposed = true
      window.clearTimeout(timer)
    }
  }, [runId])

  if (error) return <ErrorBanner text={error} />
  if (!run) return <EmptyState text="Загрузка run…" />
  if (run.status !== 'completed') return <ProcessingPage run={run} />
  return <ResultPage run={run} />
}

function ProcessingPage({ run }: { run: PipelineRun }) {
  const failed = run.status === 'processing_failed'
  return (
    <div className="page narrow-page">
      <PageHeader
        eyebrow={failed ? 'Ошибка обработки' : 'Pipeline работает'}
        title={run.source_name}
        description={run.status_message ?? 'Ожидание обновления статуса'}
      />
      <section className="processing-panel">
        <div className="progress-number">{run.progress}%</div>
        <ProgressBar progress={run.progress} label={stageLabel(run.stage)} />
        <div className="steps">
          {[
            'preparing',
            'detection',
            'tracking',
            'classification',
            'aggregation',
            'rendering',
            'uploading_artifacts',
          ].map((stage) => (
            <div
              key={stage}
              className={stage === run.stage ? 'step active' : 'step'}
            >
              <span />
              {stageLabel(stage)}
            </div>
          ))}
        </div>
        {failed && (
          <ErrorBanner
            text={run.error_message ?? 'Pipeline завершился с ошибкой'}
          />
        )}
      </section>
    </div>
  )
}

function ResultPage({ run }: { run: PipelineRun }) {
  const [summary, setSummary] = useState<RunSummary | null>(null)
  const [objects, setObjects] = useState<RunObjects | null>(null)
  const [timeline, setTimeline] = useState<RunTimeline | null>(null)
  const [playback, setPlayback] = useState<Playback | null>(null)
  const [overlay, setOverlay] = useState<OverlayPayload | null>(null)
  const [seek, setSeek] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

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

  return (
    <div className="page">
      <PageHeader
        eyebrow="Результат"
        title={run.source_name}
        description={`${formatDuration(run.duration_sec)} · ${run.width ?? 0}×${run.height ?? 0}`}
      />

      <div className="summary-grid">
        <Metric label="Объектов" value={summary?.totals.total_objects ?? '—'} />
        <Metric
          label="Visibility index"
          value={formatNumber(summary?.totals.visibility_index)}
        />
        <Metric label="FPS" value={run.fps?.toFixed(1) ?? '—'} />
        <Metric label="Кадров" value={run.frame_count ?? '—'} />
      </div>

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
        <EmptyState text="Подготовка player…" />
      )}

      {summary && timeline && (
        <RunCharts
          brands={summary.brands}
          timeline={timeline}
          onSeek={setSeek}
        />
      )}

      <section className="panel objects-panel">
        <header>
          <h2>Лучшие объекты</h2>
          <p>Клик по карточке перематывает видео на лучший кадр.</p>
        </header>
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
                <div className="crop-placeholder">AD</div>
              )}
              <strong>{object.business_brand.toUpperCase()}</strong>
              <span>
                {Math.round(object.final_brand_conf * 100)}% ·{' '}
                {object.best_timestamp_sec.toFixed(1)}s
              </span>
            </button>
          ))}
        </div>
      </section>
    </div>
  )
}

function PageHeader({
  eyebrow,
  title,
  description,
}: {
  eyebrow: string
  title: string
  description: string
}) {
  return (
    <header className="page-header">
      <span>{eyebrow}</span>
      <h1>{title}</h1>
      <p>{description}</p>
    </header>
  )
}

function ProgressBar({ progress, label }: { progress: number; label: string }) {
  return (
    <div className="progress-block">
      <div>
        <span>{label}</span>
        <strong>{progress}%</strong>
      </div>
      <div className="progress-track">
        <span style={{ width: `${progress}%` }} />
      </div>
    </div>
  )
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="metric-card">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  )
}

function EmptyState({ text }: { text: string }) {
  return <div className="empty-state">{text}</div>
}

function ErrorBanner({ text }: { text: string }) {
  return <div className="error-banner">{text}</div>
}

function statusLabel(status: string) {
  return (
    {
      uploading: 'Загрузка',
      queued: 'В очереди',
      processing: 'Обработка',
      completed: 'Готово',
      processing_failed: 'Ошибка',
    }[status] ?? status
  )
}

function stageLabel(stage: string) {
  return (
    {
      queued: 'В очереди',
      preparing: 'Подготовка',
      detection: 'Детекция',
      tracking: 'Трекинг',
      classification: 'Классификация',
      aggregation: 'Агрегация',
      rendering: 'Рендеринг',
      uploading_artifacts: 'Сохранение результатов',
      completed: 'Готово',
    }[stage] ?? stage
  )
}

function formatDuration(value: number | null) {
  if (!value) return '—'
  const minutes = Math.floor(value / 60)
  const seconds = Math.round(value % 60)
  return `${minutes}:${String(seconds).padStart(2, '0')}`
}

function formatBytes(value: number) {
  if (value < 1024 ** 2) return `${Math.round(value / 1024)} KB`
  return `${(value / 1024 ** 2).toFixed(1)} MB`
}

function formatNumber(value: number | undefined) {
  return value === undefined
    ? '—'
    : new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 }).format(value)
}

export default App
