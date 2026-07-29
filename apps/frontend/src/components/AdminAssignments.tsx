import { useEffect, useState } from 'react'
import { createAssignment, getRouteAssignments, updateAssignment } from '../api'
import { AssignmentForm } from './AssignmentForm'
import { EmptyState, ErrorBanner } from './common/Feedback'
import { Select } from './common/Select'
import type { Assignment, AssignmentPayload, Route } from '../types'
import { formatDateTime } from '../utils/formatters'

interface AdminAssignmentsProps {
  citySlug: string
  /** Маршруты города со скрытыми: на скрытом маршруте задание тоже правят. */
  routes: Route[]
}

function errorMessage(reason: unknown): string {
  return reason instanceof Error ? reason.message : String(reason)
}

function plannedWindow(assignment: Assignment): string {
  const { planned_start_at: start, planned_end_at: end } = assignment
  if (!start && !end) return 'окно не задано'
  return `${start ? formatDateTime(start) : '…'} — ${end ? formatDateTime(end) : '…'}`
}

/**
 * Задания маршрута: здесь их заводят, правят и скрывают.
 *
 * Раньше кнопка «Новое задание» стояла на странице маршрута и не спрашивала
 * ничего. Задание — рамка, в которой считаются метрики маршрута: у него
 * постановщик, плановое окно и набор проездов, и заводить его должен тот, кто
 * за маршрут отвечает, а не тот, кто в этот день сел за руль. Съёмки и
 * загрузка видео остались открытыми — закрыть их значило бы сделать продукт
 * непригодным.
 *
 * Удаления нет и не будет: у задания на FK висят съёмки с CASCADE, снос утащил
 * бы видео вместе с историей. «Скрыть» убирает задание отовсюду — из списка
 * маршрута, из выпадашки загрузки, из общего списка видео и **из метрики
 * маршрута вместе со своими съёмками**. Последнее и есть смысл кнопки: раз
 * кампанию спрятали, её проезды не должны тянуть за собой средние. Механизм
 * тот же, что у периода дат, — список съёмок укорачивается до расчёта.
 *
 * «Показать» стоит рядом с «Скрыть», на одном экране: скрытие без возврата —
 * односторонняя дверь, на которой в этом проекте уже погорели города.
 */
export function AdminAssignments({ citySlug, routes }: AdminAssignmentsProps) {
  const [routeSlug, setRouteSlug] = useState(routes[0]?.slug ?? '')
  // Данные помечены маршрутом, чьи они. Вкладка не перемонтируется при смене
  // маршрута в выпадашке, и без метки на экране остался бы список предыдущего
  // — а «Скрыть» в нём относился бы уже к чужому заданию.
  const [loaded, setLoaded] = useState<{ routeSlug: string; items: Assignment[] } | null>(
    null,
  )
  const [creating, setCreating] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [formError, setFormError] = useState<string | null>(null)

  const [version, setVersion] = useState(0)
  const reload = () => setVersion((current) => current + 1)

  const activeRoute = routes.find((route) => route.slug === routeSlug) ?? null

  useEffect(() => {
    if (!routeSlug) return
    let disposed = false
    getRouteAssignments(citySlug, routeSlug, true)
      .then((page) => {
        if (!disposed) setLoaded({ routeSlug, items: page.items })
      })
      .catch((reason) => !disposed && setError(errorMessage(reason)))
    return () => {
      disposed = true
    }
  }, [citySlug, routeSlug, version])

  // Читаем только то, что относится к выбранному сейчас маршруту. null здесь
  // заодно значит «ещё не загрузили» — экран скажет об этом вместо «пусто».
  const current = loaded?.routeSlug === routeSlug ? loaded : null

  const run = async (action: () => Promise<unknown>) => {
    setBusy(true)
    setError(null)
    try {
      await action()
      reload()
    } catch (reason) {
      setError(errorMessage(reason))
    } finally {
      setBusy(false)
    }
  }

  const submitNew = (payload: AssignmentPayload) => {
    setBusy(true)
    setFormError(null)
    createAssignment(citySlug, routeSlug, payload)
      .then(() => {
        setCreating(false)
        reload()
      })
      .catch((reason) => setFormError(errorMessage(reason)))
      .finally(() => setBusy(false))
  }

  const submitEdit = (assignment: Assignment, payload: AssignmentPayload) => {
    setBusy(true)
    setFormError(null)
    updateAssignment(assignment.id, payload)
      .then(() => {
        setEditingId(null)
        reload()
      })
      .catch((reason) => setFormError(errorMessage(reason)))
      .finally(() => setBusy(false))
  }

  const toggle = (assignment: Assignment) =>
    run(() => updateAssignment(assignment.id, { is_active: !assignment.is_active }))

  const editing = current?.items.find((item) => item.id === editingId) ?? null

  return (
    <section className="panel catalog-panel">
      <h2>Задания</h2>
      <p className="catalog-hint">
        Кампания на маршруте: серия проездов с плановым окном и постановщиком.
        Видео грузят внутрь задания, и метрики маршрута считаются по его съёмкам.
      </p>

      {error && <ErrorBanner text={error} />}

      {routes.length === 0 ? (
        <EmptyState text="В городе нет маршрутов. Заведите маршрут на соседней вкладке." />
      ) : (
        <>
          <div className="geozone-fields">
            <label className="field">
              Маршрут
              <Select
                ariaLabel="Маршрут"
                value={routeSlug}
                options={routes.map((route) => ({
                  value: route.slug,
                  label: route.is_active ? route.name : `${route.name} · скрыт`,
                }))}
                disabled={busy}
                onChange={(value) => {
                  setRouteSlug(value)
                  setCreating(false)
                  setEditingId(null)
                  setError(null)
                }}
              />
            </label>
          </div>

          {!creating && !editing && (
            <div className="geozone-form-actions">
              <button
                className="primary"
                disabled={busy || !activeRoute}
                onClick={() => {
                  setCreating(true)
                  setFormError(null)
                }}
              >
                Новое задание
              </button>
            </div>
          )}

          {creating && (
            <AssignmentForm
              submitLabel="Создать задание"
              busy={busy}
              error={formError}
              onSubmit={submitNew}
              onCancel={() => {
                setCreating(false)
                setFormError(null)
              }}
            />
          )}

          {editing && (
            <AssignmentForm
              key={editing.id}
              initial={editing}
              submitLabel="Сохранить"
              busy={busy}
              error={formError}
              onSubmit={(payload) => submitEdit(editing, payload)}
              onCancel={() => {
                setEditingId(null)
                setFormError(null)
              }}
            />
          )}

          {current === null && <p className="catalog-state">Загружаем задания…</p>}

          {current !== null && current.items.length === 0 && (
            <EmptyState text="На маршруте ещё нет заданий. Создайте первое." />
          )}

          {current !== null && current.items.length > 0 && (
            <ul className="geozone-list">
              {current.items.map((assignment) => (
                <li
                  key={assignment.id}
                  className={`geozone-row${assignment.is_active ? '' : ' is-hidden-row'}`}
                >
                  <div className="geozone-row-copy">
                    <span className="geozone-row-name">{assignment.title}</span>
                    <span className="geozone-row-range">
                      {assignment.author?.full_name ?? 'постановщик не указан'} ·{' '}
                      {plannedWindow(assignment)} · {assignment.video_count} видео
                      {!assignment.is_active && ' · скрыто'}
                    </span>
                    {assignment.description && (
                      <p className="geozone-row-description">{assignment.description}</p>
                    )}
                  </div>
                  <span className="row-actions">
                    <button
                      className="ghost-button"
                      disabled={busy}
                      onClick={() => {
                        setEditingId(assignment.id)
                        setCreating(false)
                        setFormError(null)
                      }}
                    >
                      Правка
                    </button>
                    <button
                      className={assignment.is_active ? 'geozone-delete' : 'primary'}
                      disabled={busy}
                      onClick={() => void toggle(assignment)}
                    >
                      {assignment.is_active ? 'Скрыть' : 'Показать'}
                    </button>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  )
}
