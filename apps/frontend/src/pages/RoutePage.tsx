import { useEffect, useState } from 'react'
import { getCity, getRouteAssignments, getRouteSummary } from '../api'
import { RouteSummaryPanel } from '../components/RouteSummaryPanel'
import { EmptyState, ErrorBanner } from '../components/common/Feedback'
import { PageHeader } from '../components/common/PageHeader'
import { RunsSkeleton } from '../components/common/Skeletons'
import { Tabs } from '../components/common/Tabs'
import {
  assignmentPath,
  navigate,
  routePath,
  type PageView,
  type RoutePeriod,
} from '../routing'
import type { Aggregate, Assignment, Route, RouteSummary } from '../types'
import { formatPeriod, pluralAssignments } from '../utils/formatters'

function assignmentProgressLabel(assignment: Assignment): string {
  const { completed, processing, queued, uploading, processing_failed } =
    assignment.status_counts
  const parts: string[] = []
  if (completed) parts.push(`Готово ${completed}`)
  if (processing + queued + uploading) {
    parts.push(`В работе ${processing + queued + uploading}`)
  }
  if (processing_failed) parts.push(`Ошибок ${processing_failed}`)
  return parts.join(' · ') || 'Пусто'
}

const VIEW_TABS = [
  { value: 'work', label: 'Задания' },
  { value: 'analytics', label: 'Аналитика' },
]

export function RoutePage({
  citySlug,
  routeSlug,
  period,
  view,
}: {
  citySlug: string
  routeSlug: string
  period: RoutePeriod
  view: PageView
}) {
  const [route, setRoute] = useState<Route | null>(null)
  const [cityName, setCityName] = useState('')
  const [assignments, setAssignments] = useState<Assignment[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [summary, setSummary] = useState<RouteSummary | null>(null)
  // Оценка живёт на странице, а не в панели: панель размонтируется при уходе на
  // вкладку заданий, а выбранная медиана это пережить должна. Среднее по
  // умолчанию — оно слышит каждый проезд; медиана показывает те же съёмки без
  // влияния выбившегося.
  const [aggregate, setAggregate] = useState<Aggregate>('mean')

  useEffect(() => {
    let disposed = false
    const load = () => {
      Promise.all([getCity(citySlug), getRouteAssignments(citySlug, routeSlug)])
        .then(([city, page]) => {
          if (disposed) return
          setCityName(city.name)
          setRoute(city.routes.find((item) => item.slug === routeSlug) ?? null)
          setAssignments(page.items)
        })
        .catch((reason) => {
          if (!disposed) setError(String(reason))
        })
        .finally(() => {
          if (!disposed) setLoading(false)
        })
    }
    load()
    // Задания показывают статус обработки — он меняется без нашего участия.
    const interval = window.setInterval(load, 5000)
    return () => {
      disposed = true
      window.clearInterval(interval)
    }
  }, [citySlug, routeSlug])

  const totalVideos = assignments.reduce(
    (sum, assignment) => sum + assignment.video_count,
    0,
  )
  const completedVideos = assignments.reduce(
    (sum, assignment) => sum + assignment.status_counts.completed,
    0,
  )

  // Сводка маршрута читает tracks.csv каждой готовой съёмки, поэтому её нельзя
  // тянуть на пятисекундном таймере вместе с заданиями. Перечитываем только
  // когда обработалась ещё одна съёмка (это видно по счётчикам заданий) или
  // когда поменяли период — там список съёмок другой, а считать его должен
  // сервер: вторая реализация усреднения разошлась бы с первой.
  // Границы разбираем на строки: объект периода приезжает из разбора адреса и
  // при каждом переходе новый, даже если даты те же. По самим датам эффект
  // срабатывает ровно тогда, когда окно действительно поменялось.
  // Вкладка в зависимостях не для красоты: пока открыта работа, запрос не
  // уходит вообще. Раньше он уходил при каждом открытии страницы, даже когда
  // человек зашёл найти видео и цифры ему не нужны.
  const { from: periodFrom, to: periodTo } = period
  const analytics = view === 'analytics'

  useEffect(() => {
    if (!analytics) return
    let disposed = false
    getRouteSummary(citySlug, routeSlug, { from: periodFrom, to: periodTo })
      .then((loaded) => {
        if (!disposed) setSummary(loaded)
      })
      .catch(() => undefined)
    return () => {
      disposed = true
    }
  }, [analytics, citySlug, routeSlug, completedVideos, periodFrom, periodTo])

  return (
    <div className="page">
      <PageHeader
        eyebrow={cityName || 'Маршрут'}
        title={route?.name ?? 'Задания маршрута'}
        description={
          route
            ? `${pluralAssignments(assignments.length)} · ${totalVideos} видео`
            : undefined
        }
      />

      {error && <ErrorBanner text={error} />}

      {route?.description && <p className="route-description">{route.description}</p>}

      {/* Работа и цифры разведены по вкладкам: аналитика — это тысяча с лишним
          пикселей графиков, и держать её над списком заданий значило бы
          отправлять в прокрутку каждого, кто зашёл за конкретным видео. */}
      <div className="page-view-tabs">
        <Tabs
          value={view}
          options={VIEW_TABS}
          ariaLabel="Что показывать"
          onChange={(next) =>
            navigate(routePath(citySlug, routeSlug, period, next as PageView))
          }
        />
      </div>

      {loading && <RunsSkeleton />}

      {analytics ? (
        summary ? (
          <section className="route-summary">
            <RouteSummaryPanel
              summary={summary}
              period={period}
              onPeriodChange={(next) =>
                navigate(routePath(citySlug, routeSlug, next, 'analytics'))
              }
              aggregate={aggregate}
              onAggregateChange={setAggregate}
            />
          </section>
        ) : (
          <RunsSkeleton />
        )
      ) : (
        <RouteWork assignments={assignments} loading={loading} error={error} />
      )}
    </div>
  )
}

/** Операционная вкладка маршрута: задания и их состояние, без единой цифры метрики. */
function RouteWork({
  assignments,
  loading,
  error,
}: {
  assignments: Assignment[]
  loading: boolean
  error: string | null
}) {
  return (
    <>
      {/* Кнопки «Новое задание» здесь больше нет: задание заводят в админке.
          Пустой маршрут поэтому не предлагает создать, а говорит, где это
          делается, — иначе экран выглядел бы сломанным. */}
      {!loading && !error && !assignments.length && (
        <EmptyState text="На этом маршруте ещё нет заданий. Их заводят в админ-панели, на вкладке «Задания»." />
      )}

      <div className="runs-grid">
        {assignments.map((assignment) => (
          <button
            className="run-card"
            key={assignment.id}
            onClick={() => navigate(assignmentPath(assignment.id))}
          >
            <div
              className="run-preview"
              style={
                assignment.route.color_hex
                  ? { borderColor: assignment.route.color_hex }
                  : undefined
              }
            >
              <span>▦</span>
            </div>
            <div className="run-copy">
              <div className="status status-queued">
                {assignment.video_count} видео
              </div>
              <h3>{assignment.title}</h3>
              <p>{assignmentProgressLabel(assignment)}</p>
              <p className="run-card-meta">
                {assignment.author?.full_name ?? 'Постановщик не указан'}
                {' · '}
                {formatPeriod(
                  assignment.planned_start_at,
                  assignment.planned_end_at,
                )}
              </p>
            </div>
          </button>
        ))}
      </div>
    </>
  )
}
