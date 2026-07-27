import { useEffect, useState } from 'react'
import { getAssignmentRuns, getAssignmentSummary, updateAssignment } from '../api'
import { RollupCharts } from '../components/RollupCharts'
import { AssignmentForm } from '../components/AssignmentForm'
import { EmptyState, ErrorBanner } from '../components/common/Feedback'
import { Metric } from '../components/common/Metric'
import { PageHeader } from '../components/common/PageHeader'
import { RunCard } from '../components/common/RunCard'
import { RunsSkeleton } from '../components/common/Skeletons'
import { navigate, uploadPath } from '../routing'
import type {
  AssignmentPayload,
  MetricStat,
  AssignmentSummary,
  PipelineRun,
} from '../types'
import {
  formatDuration,
  formatNumber,
  formatPeriod,
  pluralShootings,
} from '../utils/formatters'

/** Обработка идёт минутами — чаще смотреть незачем. */
const POLL_INTERVAL_MS = 20000

function stat(value: MetricStat, digits = 1): string {
  if (!value.mean) return '—'
  const mean = formatNumber(Number(value.mean.toFixed(digits)))
  if (!value.std) return mean
  return `${mean} ± ${value.std.toFixed(digits)}`
}

export function AssignmentPage({ assignmentId }: { assignmentId: string }) {
  const [summary, setSummary] = useState<AssignmentSummary | null>(null)
  const [runs, setRuns] = useState<PipelineRun[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  // Пока есть необработанные съёмки — опрашиваем. Все готовы — таймер снимаем,
  // иначе открытая вкладка вечно тянет CSV каждой съёмки из хранилища.
  const [pending, setPending] = useState(true)
  const [editing, setEditing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)

  const save = (payload: AssignmentPayload) => {
    setSaving(true)
    setFormError(null)
    updateAssignment(assignmentId, payload)
      .then((updated) => {
        // Правим только шапку: метрики и съёмки от реквизитов не зависят,
        // перезапрашивать сводку ради них незачем.
        setSummary((current) =>
          current ? { ...current, assignment: updated } : current,
        )
        setEditing(false)
      })
      .catch((reason) => setFormError(String(reason)))
      .finally(() => setSaving(false))
  }

  useEffect(() => {
    let disposed = false
    const load = () => {
      Promise.all([
        getAssignmentSummary(assignmentId),
        getAssignmentRuns(assignmentId),
      ])
        .then(([summaryValue, runsValue]) => {
          if (disposed) return
          setSummary(summaryValue)
          setRuns(runsValue)
          setPending(
            summaryValue.totals.shootings_completed < summaryValue.totals.shootings_total,
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

  if (loading && !summary) {
    return (
      <div className="page">
        <RunsSkeleton />
      </div>
    )
  }

  if (error && !summary) {
    return (
      <div className="page">
        <PageHeader eyebrow="Города" title="Задание не найдено" />
        <ErrorBanner text={error} />
      </div>
    )
  }

  if (!summary) return null

  const { assignment, totals, brands, shootings } = summary
  const waiting = totals.shootings_total - totals.shootings_completed
  const color = assignment.route.color_hex ?? undefined

  return (
    <div className="page">
      <PageHeader
        eyebrow={`${assignment.city.name} · ${assignment.route.name}`}
        title={assignment.title}
        description={`${pluralShootings(totals.shootings_total)} · отснято ${formatDuration(
          totals.duration_sec,
        )} · обработано ${totals.shootings_completed} из ${totals.shootings_total}`}
        actions={
          editing ? undefined : (
            <div className="page-actions">
              <button
                className="secondary"
                onClick={() =>
                  navigate(`/archive/${assignment.city.slug}/${assignment.route.slug}`)
                }
              >
                К маршруту
              </button>
              <button className="secondary" onClick={() => setEditing(true)}>
                Реквизиты
              </button>
              <button
                className="primary"
                onClick={() => navigate(uploadPath({ assignmentId: assignment.id }))}
              >
                Добавить съёмку
              </button>
            </div>
          )
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

      {editing ? (
        <AssignmentForm
          initial={assignment}
          submitLabel="Сохранить"
          busy={saving}
          error={formError}
          onSubmit={save}
          onCancel={() => {
            setEditing(false)
            setFormError(null)
          }}
        />
      ) : (
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
      )}

      <div className="summary-grid">
        <Metric label="Объектов за съёмку" value={stat(totals.objects_per_shooting)} />
        <Metric
          label="Заметность за съёмку"
          value={stat(totals.visibility_per_shooting)}
        />
        <Metric label="Съёмок" value={totals.shootings_total} />
        <Metric label="Отснято" value={formatDuration(totals.duration_sec)} />
      </div>

      {totals.shootings_completed === 0 ? (
        <EmptyState
          text={
            waiting > 0
              ? `Метрики появятся, когда обработается первая съёмка. Сейчас в работе ${waiting}.`
              : 'В задании пока нет видео.'
          }
        />
      ) : (
        <>
          {waiting > 0 && (
            <p className="assignment-pending-note">
              Считаем по {totals.shootings_completed} готовым съёмкам. Ещё {waiting} в
              работе — данные обновятся после обработки.
            </p>
          )}
          <RollupCharts brands={brands} shootings={shootings} />
        </>
      )}

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
    </div>
  )
}
