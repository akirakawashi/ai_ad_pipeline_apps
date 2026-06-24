import { useEffect, useMemo, useState, type ReactNode } from 'react'
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

const PIPELINE_STAGES = [
  {
    key: 'queued',
    label: 'В очереди',
    description: 'Файл загружен в хранилище. Ждём, когда освободится обработчик.',
  },
  {
    key: 'preparing',
    label: 'Подготовка',
    description: 'Видео обрабатывается, проверяем длительность, FPS, размер кадра и т. д.',
  },
  {
    key: 'detection',
    label: 'Детекция',
    description: 'Анализ видео - ищем рекламные конструкции в кадрах.',
  },
  {
    key: 'tracking',
    label: 'Трекинг',
    description: 'Собираем трек по видеопотоку и объединяем с объектами на видео.',
  },
  {
    key: 'classification',
    label: 'Классификация',
    description: 'Лучшие фрагменты отдаем классификатору и определяем бренд.',
  },
  {
    key: 'aggregation',
    label: 'Расчёт метрик',
    description: 'Считаем количество объектов, заметность и уверенность по брендам.',
  },
  {
    key: 'rendering',
    label: 'Подготовка просмотра',
    description: 'Готовим видео с разметкой и данные для графиков.',
  },
  {
    key: 'uploading_artifacts',
    label: 'Сохранение результата',
    description: 'Сохраняем таблицы, кадры объектов, графики и итоговое видео.',
  },
]

function currentRoute(): Route {
  if (window.location.pathname === '/runs/new') return { page: 'new' }
  const match = window.location.pathname.match(/^\/runs\/([^/]+)$/)
  if (match) return { page: 'run', runId: match[1] }
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
      <aside className="side-rail" aria-label="Навигация">
        <div className="rail-brand">
          <span>AI</span>
        </div>
        <nav className="rail-nav">
          <button
            className={route.page === 'runs' ? 'active' : ''}
            onClick={() => navigate('/runs')}
          >
            <span>▦</span>
            Архив
          </button>
          <button
            className={route.page === 'new' ? 'active' : ''}
            onClick={() => navigate('/runs/new')}
          >
            <span>↑</span>
            Новое видео
          </button>
        </nav>
      </aside>
      <div className="workspace">
        <header className="workspace-header">
          <div className="workspace-header-inner">
            <div className="topbar-left">
              {route.page !== 'runs' && (
                <button className="back-button" onClick={() => navigate('/runs')}>
                  ‹ Назад
                </button>
              )}
              <div className="topbar-title">
                <span>Аналитика рекламы</span>
                <strong>{workspaceTitle(route)}</strong>
              </div>
            </div>
            <div className="topbar-status">
              <span />
              Сервис активен
            </div>
          </div>
        </header>
        <main className="workspace-main">
          {route.page === 'runs' && <RunsPage />}
          {route.page === 'new' && <UploadPage />}
          {route.page === 'run' && <RunPage runId={route.runId} />}
        </main>
      </div>
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
        eyebrow="Архив"
        title="Обработанные видео"
        actions={
          <button className="primary" onClick={() => navigate('/runs/new')}>
            Добавить видео
          </button>
        }
      />
      {loading && <RunsSkeleton />}
      {error && <ErrorBanner text={error} />}
      {!loading && !runs.length && (
        <EmptyState
          text="Здесь пока нет обработанных видео."
          action={
            <button className="primary" onClick={() => navigate('/runs/new')}>
              Добавить первое видео
            </button>
          }
        />
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
  const [dragActive, setDragActive] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const selectFile = (nextFile: File | null) => {
    if (busy) return
    setFile(nextFile)
    setProgress(0)
    setError(null)
  }

  const startUpload = async () => {
    if (!file) return
    setBusy(true)
    setProgress(0)
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
        eyebrow="Загрузка"
        title="Добавьте видео маршрута"
        description="Выберите файл или перетащите его в окно. Мы загрузим видео и сразу запустим анализ."
        actions={
          <button className="secondary" onClick={() => navigate('/runs')}>
            В архив
          </button>
        }
      />
      <section
        className={`upload-panel${dragActive ? ' drag-active' : ''}${
          busy ? ' busy' : ''
        }`}
        onDragEnter={(event) => {
          event.preventDefault()
          setDragActive(true)
        }}
        onDragOver={(event) => {
          event.preventDefault()
          setDragActive(true)
        }}
        onDragLeave={(event) => {
          event.preventDefault()
          setDragActive(false)
        }}
        onDrop={(event) => {
          event.preventDefault()
          setDragActive(false)
          selectFile(event.dataTransfer.files[0] ?? null)
        }}
      >
        <div className="upload-icon">↑</div>
        <h2>{file ? 'Файл выбран' : 'Перетащите видео сюда'}</h2>
        <p>
          {file
            ? 'Если всё верно, можно начинать анализ.'
            : 'Подойдут MP4, MOV, MKV и WebM'}
        </p>

        {file && <FileCard file={file} />}

        <div className="upload-actions">
          <label className="secondary file-button">
            {file ? 'Выбрать другое' : 'Выбрать видео'}
            <input
              type="file"
              accept="video/*,.mkv"
              disabled={busy}
              onChange={(event) => selectFile(event.target.files?.[0] ?? null)}
            />
          </label>
          {file && !busy && (
            <button className="ghost-button" onClick={() => selectFile(null)}>
              Убрать файл
            </button>
          )}
        </div>

        {busy && (
          <div className="upload-progress-card">
            <InfinityLoader compact />
            <div>
              <h3>Загружаем видео</h3>
              <p>
                Сохраняем исходный файл. Если ролик большой, это может занять
                пару минут.
              </p>
            </div>
            <ProgressBar progress={progress} label="Файл загружается" animated />
          </div>
        )}
        {error && <ErrorBanner text={error} />}
        <button
          className="primary action-button"
          disabled={!file || busy}
          onClick={() => void startUpload()}
        >
          {busy ? 'Загружаем…' : 'Начать анализ'}
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
  if (!run) return <EmptyState text="Открываем анализ…" />
  if (run.status !== 'completed') return <ProcessingPage run={run} />
  return <ResultPage run={run} />
}

function ProcessingPage({ run }: { run: PipelineRun }) {
  const failed = run.status === 'processing_failed'
  return (
    <div className="page narrow-page">
      <PageHeader
        eyebrow={failed ? 'Обработка не прошла' : 'Видео обрабатывается'}
        title={run.source_name}
        description={run.status_message ?? 'Ждём первый статус от обработчика'}
        actions={
          <div className="page-actions">
            <button className="secondary" onClick={() => navigate('/runs')}>
              В архив
            </button>
            <button className="primary" onClick={() => navigate('/runs/new')}>
              Добавить видео
            </button>
          </div>
        }
      />
      <section className={`processing-panel${failed ? ' failed' : ''}`}>
        <div className="processing-hero">
          <InfinityLoader />
          <div>
            <div className="progress-number">{run.progress}%</div>
            <div className="processing-now">
              <strong>
                {stageLabel(run.stage)}
                {!failed && <AnimatedDots />}
              </strong>
              <p>{stageDescription(run.stage)}</p>
            </div>
          </div>
        </div>
        <ProgressBar
          progress={run.progress}
          label={stageLabel(run.stage)}
          animated={!failed}
        />
        <PipelineSteps activeStage={run.stage} failed={failed} />
        {failed && (
          <ErrorBanner
            text={run.error_message ?? 'Анализ остановился с ошибкой'}
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
        eyebrow="Результат анализа"
        title={run.source_name}
        description={`${formatDuration(run.duration_sec)} · ${run.width ?? 0}×${run.height ?? 0}`}
        actions={
          <div className="page-actions">
            <button className="secondary" onClick={() => navigate('/runs')}>
              В архив
            </button>
            <button className="secondary" onClick={() => void copyResultLink()}>
              {copied ? 'Скопировано' : 'Копировать ссылку'}
            </button>
            <button className="primary" onClick={() => navigate('/runs/new')}>
              Добавить видео
            </button>
          </div>
        }
      />

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

function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow: string
  title: string
  description?: string
  actions?: ReactNode
}) {
  return (
    <header className="page-header">
      <div>
        <span>{eyebrow}</span>
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {actions && <div className="page-header-actions">{actions}</div>}
    </header>
  )
}

function ProgressBar({
  progress,
  label,
  animated = false,
}: {
  progress: number
  label: string
  animated?: boolean
}) {
  return (
    <div className={`progress-block${animated ? ' animated' : ''}`}>
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

function FileCard({ file }: { file: File }) {
  return (
    <div className="file-card">
      <div className="file-card-icon">▶</div>
      <div>
        <strong>{file.name}</strong>
        <span>
          {formatBytes(file.size)} · {file.type || 'video'}
        </span>
      </div>
    </div>
  )
}

function InfinityLoader({ compact = false }: { compact?: boolean }) {
  return (
    <div className={`infinity-loader${compact ? ' compact' : ''}`} aria-hidden>
      <svg viewBox="0 0 120 60" role="img">
        <path
          className="infinity-path infinity-path-base"
          d="M30 30 C30 11 55 11 60 30 C65 49 90 49 90 30 C90 11 65 11 60 30 C55 49 30 49 30 30"
        />
        <path
          className="infinity-path infinity-path-active"
          d="M30 30 C30 11 55 11 60 30 C65 49 90 49 90 30 C90 11 65 11 60 30 C55 49 30 49 30 30"
        />
      </svg>
    </div>
  )
}

function AnimatedDots() {
  return (
    <span className="animated-dots" aria-hidden>
      <span />
      <span />
      <span />
    </span>
  )
}

function PipelineSteps({
  activeStage,
  failed,
}: {
  activeStage: string
  failed: boolean
}) {
  const activeIndex = PIPELINE_STAGES.findIndex(
    (stage) => stage.key === activeStage,
  )
  return (
    <div className="steps">
      {PIPELINE_STAGES.map((stage, index) => {
        const done = activeIndex !== -1 && index < activeIndex
        const active = stage.key === activeStage
        const failedActive = failed && active
        return (
          <div
            key={stage.key}
            className={[
              'step',
              done ? 'done' : '',
              active ? 'active' : '',
              failedActive ? 'failed' : '',
            ]
              .filter(Boolean)
              .join(' ')}
          >
            <span />
            <div>
              <strong>{stage.label}</strong>
              <small>{stage.description}</small>
            </div>
          </div>
        )
      })}
    </div>
  )
}

function RunsSkeleton() {
  return (
    <div className="runs-grid skeleton-grid" aria-label="Загружаем архив">
      {Array.from({ length: 6 }).map((_, index) => (
        <div className="run-card skeleton-card" key={index}>
          <SkeletonBlock className="run-preview-skeleton" />
          <div className="run-copy">
            <SkeletonBlock className="skeleton-pill" />
            <SkeletonBlock className="skeleton-line wide" />
            <SkeletonBlock className="skeleton-line" />
          </div>
        </div>
      ))}
    </div>
  )
}

function MetricSkeletonGrid() {
  return (
    <div className="summary-grid" aria-label="Загружаем метрики">
      {Array.from({ length: 4 }).map((_, index) => (
        <div className="metric-card skeleton-card" key={index}>
          <SkeletonBlock className="skeleton-line short" />
          <SkeletonBlock className="skeleton-value" />
        </div>
      ))}
    </div>
  )
}

function PlayerSkeleton() {
  return (
    <section className="panel player-panel player-skeleton">
      <SkeletonBlock className="player-skeleton-frame" />
    </section>
  )
}

function ChartsSkeleton() {
  return (
    <div className="charts-grid charts-skeleton" aria-label="Загружаем графики">
      <section className="panel chart-card skeleton-card">
        <SkeletonBlock className="skeleton-line wide" />
        <SkeletonBlock className="chart-skeleton-frame" />
      </section>
      <section className="panel chart-card skeleton-card">
        <SkeletonBlock className="skeleton-line wide" />
        <SkeletonBlock className="chart-skeleton-frame" />
      </section>
      <section className="panel chart-card timeline-chart skeleton-card">
        <SkeletonBlock className="skeleton-line wide" />
        <SkeletonBlock className="timeline-skeleton-frame" />
      </section>
    </div>
  )
}

function ObjectsSkeleton() {
  return (
    <section
      className="panel objects-panel skeleton-card"
      aria-label="Загружаем объекты"
    >
      <header>
        <SkeletonBlock className="skeleton-line wide" />
        <SkeletonBlock className="skeleton-line" />
      </header>
      <div className="objects-grid">
        {Array.from({ length: 8 }).map((_, index) => (
          <div className="object-card object-skeleton-card" key={index}>
            <SkeletonBlock className="object-skeleton-image" />
            <SkeletonBlock className="skeleton-line wide" />
            <SkeletonBlock className="skeleton-line" />
          </div>
        ))}
      </div>
    </section>
  )
}

function SkeletonBlock({ className = '' }: { className?: string }) {
  return <span className={`skeleton-block ${className}`} />
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="metric-card">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  )
}

function EmptyState({ text, action }: { text: string; action?: ReactNode }) {
  return (
    <div className="empty-state">
      <span>{text}</span>
      {action && <div className="empty-action">{action}</div>}
    </div>
  )
}

function ErrorBanner({ text }: { text: string }) {
  return <div className="error-banner">{text}</div>
}

function statusLabel(status: string) {
  return (
    {
      uploading: 'Загружается',
      queued: 'В очереди',
      processing: 'Идёт анализ',
      completed: 'Готово',
      processing_failed: 'Ошибка анализа',
    }[status] ?? status
  )
}

function stageLabel(stage: string) {
  if (stage === 'completed') return 'Готово'
  return PIPELINE_STAGES.find((item) => item.key === stage)?.label ?? stage
}

function stageDescription(stage: string) {
  if (stage === 'completed') return 'Готово. Можно смотреть видео и графики.'
  return (
    PIPELINE_STAGES.find((item) => item.key === stage)?.description ??
    'Ждём обновление статуса.'
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

function workspaceTitle(route: Route) {
  if (route.page === 'new') return 'Загрузка видео'
  if (route.page === 'run') return 'Результат'
  return 'Архив'
}

export default App
