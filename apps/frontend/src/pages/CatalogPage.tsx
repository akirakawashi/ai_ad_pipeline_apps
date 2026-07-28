import { useEffect, useState } from 'react'
import { getAdStructures, getCatalogImports, getCities } from '../api'
import { EmptyState, ErrorBanner } from '../components/common/Feedback'
import { PageHeader } from '../components/common/PageHeader'
import { Select } from '../components/common/Select'
import type { AdStructure, CatalogImport, City } from '../types'

function errorMessage(reason: unknown): string {
  return reason instanceof Error ? reason.message : String(reason)
}

/**
 * Справочник рекламных конструкций города — только чтение.
 *
 * Загрузка паков и откат ревизий отсюда убраны в админ-панель: заменить каталог
 * целиком — административное действие, и держать его на экране, куда приходят
 * посмотреть список, значило класть кнопку «Удалить ревизию» под руку тому, кто
 * искал адрес. Историю ревизий страница всё же читает — из неё берётся номер
 * текущей, без него непонятно, на что смотришь.
 */
export function CatalogPage() {
  const [cities, setCities] = useState<City[]>([])
  const [citySlug, setCitySlug] = useState('')
  const [structures, setStructures] = useState<AdStructure[]>([])
  const [total, setTotal] = useState(0)
  const [imports, setImports] = useState<CatalogImport[]>([])
  const [search, setSearch] = useState('')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getCities()
      .then((list) => {
        setCities(list)
        setCitySlug((current) => current || list[0]?.slug || '')
      })
      .catch((reason) => setError(errorMessage(reason)))
  }, [])

  useEffect(() => {
    if (!citySlug) return
    let disposed = false

    Promise.all([
      getAdStructures(citySlug, { search: search || undefined }),
      getCatalogImports(citySlug),
    ])
      .then(([page, history]) => {
        if (disposed) return
        setStructures(page.items)
        setTotal(page.total)
        setImports(history)
      })
      .catch((reason) => {
        if (!disposed) setError(errorMessage(reason))
      })

    return () => {
      disposed = true
    }
  }, [citySlug, search])

  const currentRevision = imports.find((item) => item.is_current)

  return (
    <div className="page">
      <PageHeader
        eyebrow="Каталог"
        title="Рекламные конструкции"
        description="Конструкции текущей ревизии города. Загружаются паком файлов в админ-панели."
      />

      {error && <ErrorBanner text={error} />}

      <section className="filter-bar">
        <div className="field">
          Город
          <Select
            ariaLabel="Город"
            value={citySlug}
            options={cities.map((city) => ({ value: city.slug, label: city.name }))}
            onChange={setCitySlug}
          />
        </div>
        <p className="catalog-state">
          {currentRevision
            ? `Ревизия ${currentRevision.revision} · точек: ${total}`
            : 'Каталог пуст'}
        </p>
      </section>

      <section className="panel catalog-panel">
        <h2>Конструкции</h2>
        <input
          className="text-input catalog-search"
          type="search"
          placeholder="Поиск по адресу"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
        {structures.length === 0 ? (
          <EmptyState text="Каталог пуст. Пак файлов загружается в админ-панели." />
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Адрес</th>
                  <th className="numeric">Поверхностей</th>
                  <th className="numeric">Координаты</th>
                </tr>
              </thead>
              <tbody>
                {structures.map((structure) => (
                  <tr key={structure.id}>
                    <td>{structure.address}</td>
                    <td className="numeric">{structure.surfaces_count}</td>
                    <td className="numeric">
                      {structure.latitude.toFixed(6)}, {structure.longitude.toFixed(6)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}
