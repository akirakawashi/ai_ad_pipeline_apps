import { useEffect, useState } from 'react'
import { createUser, getUsers } from '../../api'
import { Select } from './Select'
import type { User } from '../../types'

interface UserSelectProps {
  /** id человека либо '' — не выбран. */
  value: string
  onChange: (userId: string) => void
  label: string
  placeholder?: string
  disabled?: boolean
  /**
   * Уже выбранный человек, если он мог выпасть из справочника.
   *
   * Список отдаёт только активных, поэтому у задания с уволившимся автором
   * выбранное значение не нашлось бы среди вариантов — селектор показал бы
   * плейсхолдер, будто автора нет. Подмешиваем его вручную.
   */
  current?: User | null
}

/**
 * Выбор человека из справочника с созданием прямо здесь.
 *
 * Создание на месте — сознательно вместо отдельной страницы администрирования:
 * иначе завести нового оператора означало бы идти в другой раздел посреди
 * загрузки. Полноценное управление справочником появится позже.
 *
 * Список грузится на каждый экземпляр. Он крошечный, а общий кэш пришлось бы
 * инвалидировать после создания — цена больше выигрыша.
 */
export function UserSelect({
  value,
  onChange,
  label,
  placeholder = 'Выберите человека',
  disabled,
  current,
}: UserSelectProps) {
  const [users, setUsers] = useState<User[]>([])
  const [creating, setCreating] = useState(false)
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let disposed = false
    getUsers()
      .then((result) => {
        if (!disposed) setUsers(result)
      })
      .catch((reason) => {
        if (!disposed) setError(String(reason))
      })
    return () => {
      disposed = true
    }
  }, [])

  const save = () => {
    if (!draft.trim() || busy) return
    setBusy(true)
    setError(null)
    createUser(draft)
      .then((user) => {
        setUsers((current) =>
          [...current, user].sort((a, b) => a.full_name.localeCompare(b.full_name, 'ru')),
        )
        onChange(user.id)
        setCreating(false)
        setDraft('')
      })
      .catch((reason) => setError(String(reason)))
      .finally(() => setBusy(false))
  }

  const cancel = () => {
    setCreating(false)
    setDraft('')
    setError(null)
  }

  const options = users.map((user) => ({ value: user.id, label: user.full_name }))
  if (current && value === current.id && !users.some((user) => user.id === current.id)) {
    options.unshift({
      value: current.id,
      label: `${current.full_name} (не в справочнике)`,
    })
  }

  return (
    <div className="field user-select">
      {label}
      {creating ? (
        <div className="user-select-create">
          <input
            className="text-input"
            autoFocus
            value={draft}
            placeholder="Фамилия Имя Отчество"
            disabled={busy}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                event.preventDefault()
                save()
              }
              if (event.key === 'Escape') cancel()
            }}
          />
          <button className="primary" disabled={!draft.trim() || busy} onClick={save}>
            {busy ? 'Сохраняем…' : 'Сохранить'}
          </button>
          <button className="ghost-button" disabled={busy} onClick={cancel}>
            Отмена
          </button>
        </div>
      ) : (
        <>
          <Select
            ariaLabel={label}
            value={value}
            disabled={disabled}
            placeholder={placeholder}
            options={options}
            onChange={onChange}
          />
          <button
            className="ghost-button user-select-add"
            disabled={disabled}
            onClick={() => setCreating(true)}
          >
            + Добавить человека
          </button>
        </>
      )}
      {error && <span className="user-select-error">{error}</span>}
    </div>
  )
}
