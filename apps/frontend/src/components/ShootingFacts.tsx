import { useState } from 'react'
import { updateShooting } from '../api'
import { ErrorBanner } from './common/Feedback'
import { UserSelect } from './common/UserSelect'
import type { PipelineRun } from '../types'
import {
  formatDateTime,
  isoFromLocalInput,
  localInputFromIso,
} from '../utils/formatters'

/**
 * Реквизиты съёмки: кто снимал и когда.
 *
 * Время начала подставляется при загрузке из метаданных файла и потому
 * правится: у копии с карты памяти это время копирования, а не записи.
 * Конец не редактируется — сервер выводит его из длительности видео.
 */
export function ShootingFacts({
  run,
  onUpdated,
}: {
  run: PipelineRun
  onUpdated: (run: PipelineRun) => void
}) {
  const [editing, setEditing] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [startAt, setStartAt] = useState(localInputFromIso(run.shot_started_at))
  const [operatorId, setOperatorId] = useState(run.operator?.id ?? '')

  const open = () => {
    setStartAt(localInputFromIso(run.shot_started_at))
    setOperatorId(run.operator?.id ?? '')
    setError(null)
    setEditing(true)
  }

  const save = () => {
    setBusy(true)
    setError(null)
    updateShooting(run.run_id, {
      shot_started_at: isoFromLocalInput(startAt),
      operator_user_id: operatorId || null,
    })
      .then((updated) => {
        onUpdated(updated)
        setEditing(false)
      })
      .catch((reason) => setError(String(reason)))
      .finally(() => setBusy(false))
  }

  if (editing) {
    return (
      <section className="panel assignment-form">
        <h2>Реквизиты съёмки</h2>
        <div className="assignment-form-fields">
          <div className="field">
            Начало съёмки
            <input
              type="datetime-local"
              className="text-input"
              value={startAt}
              disabled={busy}
              onChange={(event) => setStartAt(event.target.value)}
            />
          </div>
          <UserSelect
            label="Оператор"
            value={operatorId}
            current={run.operator}
            disabled={busy}
            placeholder="Кто снимал"
            onChange={setOperatorId}
          />
        </div>
        <p className="assignment-form-hint">
          Окончание считается автоматически: начало плюс длительность видео.
        </p>
        {error && <ErrorBanner text={error} />}
        <div className="assignment-form-actions">
          <button className="primary" disabled={busy} onClick={save}>
            {busy ? 'Сохраняем…' : 'Сохранить'}
          </button>
          <button
            className="ghost-button"
            disabled={busy}
            onClick={() => setEditing(false)}
          >
            Отмена
          </button>
        </div>
      </section>
    )
  }

  return (
    <dl className="assignment-facts">
      <div>
        <dt>Оператор</dt>
        <dd>{run.operator?.full_name ?? '—'}</dd>
      </div>
      <div>
        <dt>Начало съёмки</dt>
        <dd>{formatDateTime(run.shot_started_at)}</dd>
      </div>
      <div>
        <dt>Окончание съёмки</dt>
        <dd>{formatDateTime(run.shot_finished_at)}</dd>
      </div>
      <div>
        <dt> </dt>
        <dd>
          <button className="ghost-button user-select-add" onClick={open}>
            Изменить
          </button>
        </dd>
      </div>
    </dl>
  )
}
