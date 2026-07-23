import { useState } from 'react'
import { ErrorBanner } from './common/Feedback'
import { UserSelect } from './common/UserSelect'
import type { Assignment, AssignmentPayload } from '../types'
import { isoFromLocalInput, localInputFromIso } from '../utils/formatters'

interface AssignmentFormProps {
  /** Задание для правки. Отсутствует — форма создания. */
  initial?: Assignment
  submitLabel: string
  busy?: boolean
  error?: string | null
  onSubmit: (payload: AssignmentPayload) => void
  onCancel: () => void
}

/**
 * Реквизиты задания. Даты здесь — плановые: их задаёт постановщик.
 * Фактические считает сервер по временам съёмок, вводить их незачем.
 *
 * Постановщик обязателен в форме, хотя в схеме поле nullable: NOT NULL в базе
 * заблокировал бы создание задания, пока справочник людей пуст.
 */
export function AssignmentForm({
  initial,
  submitLabel,
  busy,
  error,
  onSubmit,
  onCancel,
}: AssignmentFormProps) {
  const [title, setTitle] = useState(initial?.title ?? '')
  const [description, setDescription] = useState(initial?.description ?? '')
  const [authorId, setAuthorId] = useState(initial?.author?.id ?? '')
  const [startAt, setStartAt] = useState(
    localInputFromIso(initial?.planned_start_at ?? null),
  )
  const [endAt, setEndAt] = useState(localInputFromIso(initial?.planned_end_at ?? null))

  const windowBroken = Boolean(startAt && endAt && endAt < startAt)
  const canSubmit = Boolean(authorId) && !windowBroken && !busy

  const submit = () => {
    if (!canSubmit) return
    onSubmit({
      title: title.trim() || null,
      description: description.trim() || null,
      planned_start_at: isoFromLocalInput(startAt),
      planned_end_at: isoFromLocalInput(endAt),
      author_user_id: authorId,
    })
  }

  return (
    <section className="panel assignment-form">
      <h2>{initial ? 'Реквизиты задания' : 'Новое задание'}</h2>

      <div className="assignment-form-fields">
        <div className="field assignment-form-wide">
          Название
          <input
            className="text-input"
            value={title}
            placeholder={
              initial
                ? initial.title
                : 'Например: Летний замер, первая неделя августа'
            }
            disabled={busy}
            onChange={(event) => setTitle(event.target.value)}
          />
        </div>

        <UserSelect
          label="Постановщик"
          value={authorId}
          disabled={busy}
          onChange={setAuthorId}
        />

        <div className="field">
          Плановое начало
          <input
            type="datetime-local"
            className="text-input"
            value={startAt}
            disabled={busy}
            onChange={(event) => setStartAt(event.target.value)}
          />
        </div>

        <div className="field">
          Плановое окончание
          <input
            type="datetime-local"
            className="text-input"
            value={endAt}
            disabled={busy}
            onChange={(event) => setEndAt(event.target.value)}
          />
        </div>

        <div className="field assignment-form-wide">
          Описание
          <textarea
            className="text-area"
            value={description}
            placeholder="Зачем снимаем, на что обратить внимание"
            disabled={busy}
            onChange={(event) => setDescription(event.target.value)}
          />
        </div>
      </div>

      {windowBroken && (
        <ErrorBanner text="Окончание задания не может быть раньше его начала." />
      )}
      {error && <ErrorBanner text={error} />}
      {!authorId && (
        <p className="assignment-form-hint">
          Укажите постановщика — без него задание не создать.
        </p>
      )}

      <div className="assignment-form-actions">
        <button className="primary" disabled={!canSubmit} onClick={submit}>
          {busy ? 'Сохраняем…' : submitLabel}
        </button>
        <button className="ghost-button" disabled={busy} onClick={onCancel}>
          Отмена
        </button>
      </div>
    </section>
  )
}
