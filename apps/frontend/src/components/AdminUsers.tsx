import { useEffect, useState } from 'react'
import { createUser, getUsers, updateUser } from '../api'
import { EmptyState, ErrorBanner } from './common/Feedback'
import type { User } from '../types'

function errorMessage(reason: unknown): string {
  return reason instanceof Error ? reason.message : String(reason)
}

function formatMoment(value: string | null): string {
  if (!value) return '—'
  return new Date(value).toLocaleDateString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  })
}

/**
 * Справочник людей: кто загружает видео и паки каталога. Единственное место, где
 * человек заводится.
 *
 * Раньше его заводили прямо из выпадашки «Кто загрузил» в форме загрузки, а
 * посмотреть список, исправить опечатку в фамилии или убрать уволившегося было
 * неоткуда — `PATCH /users/{id}` существовал и не вызывался ни разу. Справочник
 * копил близнецов: «Иванов», «Иванов А.», «иванов» — заводил их тот, кто в эту
 * минуту грузил видео, а не тот, кто за справочник отвечает. Теперь наоборот:
 * люди создаются здесь, а выпадашки только выбирают из готового.
 *
 * Удаления нет: человек стоит в авторах у съёмок и загрузок, снос утащил бы
 * историю. «Скрыть» убирает его из выпадашек, «Показать» возвращает — и обе
 * кнопки на одном экране, иначе это односторонняя дверь.
 */
export function AdminUsers() {
  const [users, setUsers] = useState<User[]>([])
  const [newName, setNewName] = useState('')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [version, setVersion] = useState(0)
  const reload = () => setVersion((current) => current + 1)

  useEffect(() => {
    let disposed = false
    getUsers(true)
      .then((list) => !disposed && setUsers(list))
      .catch((reason) => !disposed && setError(errorMessage(reason)))
    return () => {
      disposed = true
    }
  }, [version])

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

  const addUser = async () => {
    const name = newName.trim()
    if (!name) return
    await run(async () => {
      await createUser(name)
      setNewName('')
    })
  }

  const startEdit = (user: User) => {
    setEditingId(user.id)
    setDraft(user.full_name)
    setError(null)
  }

  const saveEdit = async (user: User) => {
    const name = draft.trim()
    if (!name || name === user.full_name) {
      setEditingId(null)
      return
    }
    await run(async () => {
      await updateUser(user.id, { full_name: name })
      setEditingId(null)
    })
  }

  const toggle = (user: User) =>
    run(() => updateUser(user.id, { is_active: !user.is_active }))

  return (
    <section className="panel catalog-panel">
      <h2>Сотрудники</h2>
      <p className="catalog-hint">
        Справочник людей для полей «Кто загрузил». Заводятся только здесь — в
        формах загрузки их выбирают из готового списка.
      </p>

      {error && <ErrorBanner text={error} />}

      <div className="geozone-fields">
        <label className="field">
          ФИО
          <input
            className="text-input"
            placeholder="Фамилия Имя Отчество"
            value={newName}
            disabled={busy}
            onChange={(event) => setNewName(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                event.preventDefault()
                void addUser()
              }
            }}
          />
        </label>
      </div>
      <div className="geozone-form-actions">
        <button className="primary" disabled={busy || !newName.trim()} onClick={addUser}>
          Добавить человека
        </button>
      </div>

      <div className="admin-users-list">
        {users.length === 0 ? (
          <EmptyState text="Справочник пуст. Заведите первого человека." />
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>ФИО</th>
                  <th>Заведён</th>
                  <th>Статус</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {users.map((user) => (
                  <tr key={user.id} className={user.is_active ? '' : 'is-hidden-row'}>
                    <td>
                      {editingId === user.id ? (
                        <input
                          className="text-input"
                          autoFocus
                          value={draft}
                          disabled={busy}
                          onChange={(event) => setDraft(event.target.value)}
                          onKeyDown={(event) => {
                            if (event.key === 'Enter') {
                              event.preventDefault()
                              void saveEdit(user)
                            }
                            if (event.key === 'Escape') setEditingId(null)
                          }}
                        />
                      ) : (
                        user.full_name
                      )}
                    </td>
                    <td>{formatMoment(user.created_at)}</td>
                    <td>{user.is_active ? 'в справочнике' : 'скрыт'}</td>
                    <td>
                      <span className="row-actions">
                        {editingId === user.id ? (
                          <>
                            <button
                              className="ghost-button"
                              disabled={busy}
                              onClick={() => void saveEdit(user)}
                            >
                              Сохранить
                            </button>
                            <button
                              className="ghost-button"
                              disabled={busy}
                              onClick={() => setEditingId(null)}
                            >
                              Отмена
                            </button>
                          </>
                        ) : (
                          <>
                            <button
                              className="ghost-button"
                              disabled={busy}
                              onClick={() => startEdit(user)}
                            >
                              Переименовать
                            </button>
                            <button
                              className="ghost-button"
                              disabled={busy}
                              onClick={() => void toggle(user)}
                            >
                              {user.is_active ? 'Скрыть' : 'Показать'}
                            </button>
                          </>
                        )}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  )
}
