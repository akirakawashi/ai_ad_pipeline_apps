import { useEffect, useState } from 'react'
import { getAssignment, getAssignmentRuns, getAssignmentSummary } from '../api'
import { RollupCharts } from '../components/RollupCharts'
import { EmptyState, ErrorBanner } from '../components/common/Feedback'
import { Metric } from '../components/common/Metric'
import { MetricsPanel } from '../components/common/MetricsPanel'
import { PageHeader } from '../components/common/PageHeader'
import { RunCard } from '../components/common/RunCard'
import { RunsSkeleton } from '../components/common/Skeletons'
import { Tabs } from '../components/common/Tabs'
import { assignmentPath, navigate, uploadPath, type PageView } from '../routing'
import type {
  Aggregate,
  Assignment,
  AssignmentSummary,
  PipelineRun,
} from '../types'
import {
  formatDuration,
  formatPeriod,
  formatStat,
  pluralShootings,
} from '../utils/formatters'

/** Обработка идёт минутами — чаще смотреть незачем. */
const POLL_INTERVAL_MS = 20000

const VIEW_TABS = [
  { value: 'work', label: 'Съёмки' },
  { value: 'analytics', label: 'Аналитика' },
]

export function AssignmentPage({
  assignmentId,
  view,
}: {
  assignmentId: string
  view: PageView
}) {
  // Задание и его съёмки — дешёвые чтения, их держим всегда: из них собрана
  // шапка. Сводка приезжает отдельно и только под вкладкой аналитики: она
  // перечитывает tracks.csv каждой готовой съёмки, и платить за это, когда
  // человек зашёл открыть конкретное видео, незачем.
  const [assignment, setAssignment] = useState<Assignment | null>(null)
  const [runs, setRuns] = useState<PipelineRun[]>([])
  const [summary, setSummary] = useState<AssignmentSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  // Пока есть необработанные съёмки — опрашиваем. Все готовы — таймер снимаем.
  const [pending, setPending] = useState(true)

  useEffect(() => {
    let disposed = false
    const load = () => {
      Promise.all([getAssignment(assignmentId), getAssignmentRuns(assignmentId)])
        .then(([assignmentValue, runsValue]) => {
          if (disposed) return
          setAssignment(assignmentValue)
          setRuns(runsValue)
          setPending(
            assignmentValue.status_counts.completed < assignmentValue.video_count,
          )
        })
        .catch((reason) => {
          if (!disposed) setError(String(reason))
        })
        .finally(() => {
          if (!disposed) setLoading(false)
        })
    }
    load()
    if (!pending) {
      return () => {
        disposed = true
      }
    }
    const interval = window.setInterval(load, POLL_INTERVAL_MS)
    return () => {
      disposed = true
      window.clearInterval(interval)
    }
  }, [assignmentId, pending])

  const completed = assignment?.status_counts.completed ?? 0
  const analytics = view === 'analytics'
  // Оценка живёт на странице, а не внутри вкладки: иначе уход за видео и
  // возврат сбрасывали бы медиану на среднее. По той же причине страница не
  // пересоздаётся при переключении вкладки (см. key в App.tsx).
  // Среднее по умолчанию: оно слышит каждый проезд. Медиана — чтобы посмотреть
  // на те же съёмки без влияния выбившегося проезда.
  const [aggregate, setAggregate] = useState<Aggregate>('mean')

  // Перечитываем сводку не по таймеру, а когда обработалась ещё одна съёмка:
  // на общем двадцатисекундном опросе она тянула бы CSV всех съёмок задания.
  useEffect(() => {
    if (!analytics) return
    let disposed = false
    getAssignmentSummary(assignmentId)
      .then((loaded) => {
        if (!disposed) setSummary(loaded)
      })
      .catch((reason) => {
        if (!disposed) setError(String(reason))
      })
    return () => {
      disposed = true
    }
  }, [analytics, assignmentId, completed])

  if (loading && !assignment) {
    return (
      <div className="page">
        <RunsSkeleton />
      </div>
    )
  }

  if (error && !assignment) {
    return (
      <div className="page">
        <PageHeader eyebrow="Города" title="Задание не найдено" />
        <ErrorBanner text={error} />
      </div>
    )
  }

  if (!assignment) return null

  const total = assignment.video_count
  const waiting = total - completed
  // Длительность считаем из съёмок: раньше её приносила сводка, но ради одной
  // цифры в шапке дёргать пересчёт всего задания — плохая сделка.
  const recordedSec = runs.reduce((sum, run) => sum + (run.duration_sec ?? 0), 0)
  const color = assignment.route.color_hex ?? undefined

  return (
    <div className="page">
      <PageHeader
        eyebrow={`${assignment.city.name} · ${assignment.route.name}`}
        title={assignment.title}
        description={`${pluralShootings(total)} · отснято ${formatDuration(
          recordedSec,
        )} · обработано ${completed} из ${total}`}
        actions={
          // Кнопки «Реквизиты» здесь нет: задание правят в админке, там же, где
          // заводят. Загрузка съёмки осталась — это работа, а не справочник.
          <div className="page-actions">
            <button
              className="secondary"
              onClick={() =>
                navigate(`/archive/${assignment.city.slug}/${assignment.route.slug}`)
              }
            >
              К маршруту
            </button>
            <button
              className="primary"
              onClick={() => navigate(uploadPath({ assignmentId: assignment.id }))}
            >
              Добавить съёмку
            </button>
          </div>
        }
      />

      <div className="assignment-heading">
        <span
          className="assignment-dot"
          style={color ? { background: color } : undefined}
        />
        <span>{assignment.route.name}</span>
      </div>

      {error && <ErrorBanner text={error} />}

      <dl className="assignment-facts">
        <div>
          <dt>Постановщик</dt>
          <dd>{assignment.author?.full_name ?? '—'}</dd>
        </div>
        <div>
          <dt>План</dt>
          <dd>
            {formatPeriod(assignment.planned_start_at, assignment.planned_end_at)}
          </dd>
        </div>
        <div>
          <dt>Факт</dt>
          <dd>
            {formatPeriod(assignment.actual_start_at, assignment.actual_end_at)}
          </dd>
        </div>
        {assignment.description && (
          <div className="assignment-facts-wide">
            <dt>Описание</dt>
            <dd>{assignment.description}</dd>
          </div>
        )}
      </dl>

      {/* Съёмки и цифры разведены: графиков больше тысячи пикселей, и держать
          их над списком видео значило бы отправлять в прокрутку каждого, кто
          зашёл открыть конкретную съёмку. */}
      <div className="page-view-tabs">
        <Tabs
          value={view}
          options={VIEW_TABS}
          ariaLabel="Что показывать"
          onChange={(next) => navigate(assignmentPath(assignmentId, next as PageView))}
        />
      </div>

      {analytics ? (
        <AssignmentAnalytics
          summary={summary}
          waiting={waiting}
          aggregate={aggregate}
          onAggregateChange={setAggregate}
        />
      ) : (
        <section className="panel objects-panel">
          <header>
            <h2>Съёмки</h2>
            <p>
              Каждое видео — отдельная съёмка маршрута. Откройте, чтобы увидеть разбор.
            </p>
          </header>
          {runs.length ? (
            <div className="runs-grid">
              {runs.map((run) => (
                <RunCard key={run.run_id} run={run} />
              ))}
            </div>
          ) : (
            <EmptyState text="В задании нет видео." />
          )}
        </section>
      )}
    </div>
  )
}

/** Вкладка цифр: плитки, переключатель оценки и графики свёртки. */
function AssignmentAnalytics({
  summary,
  waiting,
  aggregate,
  onAggregateChange,
}: {
  summary: AssignmentSummary | null
  waiting: number
  aggregate: Aggregate
  onAggregateChange: (value: Aggregate) => void
}) {
  if (!summary) return <RunsSkeleton />

  const { totals, brands, shootings } = summary

  if (totals.shootings_completed === 0) {
    return (
      <EmptyState
        text={
          waiting > 0
            ? `Метрики появятся, когда обработается первая съёмка. Сейчас в работе ${waiting}.`
            : 'В задании пока нет видео.'
        }
      />
    )
  }

  return (
    <>
      <MetricsPanel aggregate={aggregate} onAggregateChange={onAggregateChange}>
        <Metric
          label="Объектов за съёмку"
          value={formatStat(totals.objects_per_shooting, aggregate)}
        />
        <Metric
          label="Заметность за съёмку"
          value={formatStat(totals.visibility_per_shooting, aggregate)}
        />
        <Metric label="Съёмок" value={totals.shootings_total} />
        <Metric label="Отснято" value={formatDuration(totals.duration_sec)} />
      </MetricsPanel>

      {waiting > 0 && (
        <p className="assignment-pending-note">
          Считаем по {totals.shootings_completed} готовым съёмкам. Ещё {waiting} в
          работе — данные обновятся после обработки.
        </p>
      )}

      <RollupCharts brands={brands} shootings={shootings} aggregate={aggregate} />
    </>
  )
}
