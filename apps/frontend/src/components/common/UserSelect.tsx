import { useEffect, useState } from 'react'
import { getUsers } from '../../api'
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
 * Выбор человека из справочника. **Только выбор.**
 *
 * Заводить людей отсюда можно было раньше, и справочник копил близнецов:
 * «Иванов», «Иванов А.», «иванов» — потому что заводил их тот, кто в эту минуту
 * грузил видео, а не тот, кто отвечает за справочник. Теперь человек создаётся
 * в админ-панели, а здесь его только выбирают из готового списка.
 *
 * Список грузится на каждый экземпляр. Он крошечный, а общий кэш пришлось бы
 * держать свежим после правок в админке — цена больше выигрыша.
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
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let disposed = false
    getUsers()
      .then((result) => {
        if (disposed) return
        setUsers(result)
        setLoaded(true)
      })
      .catch((reason) => {
        if (!disposed) setError(String(reason))
      })
    return () => {
      disposed = true
    }
  }, [])

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
      <Select
        ariaLabel={label}
        value={value}
        disabled={disabled}
        placeholder={placeholder}
        options={options}
        onChange={onChange}
      />
      {/* Пустой справочник тупиковый: выбрать некого, а завести отсюда нельзя.
          Молчаливая пустая выпадашка читалась бы как поломка. */}
      {loaded && options.length === 0 && (
        <span className="user-select-hint">
          Справочник пуст. Людей заводят в админ-панели.
        </span>
      )}
      {error && <span className="user-select-error">{error}</span>}
    </div>
  )
}
