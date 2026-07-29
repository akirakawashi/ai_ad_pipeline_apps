import { useEffect, useState } from 'react'
import { getAdStructures, getCatalogImports, getCities } from '../api'
import { EmptyState, ErrorBanner } from '../components/common/Feedback'
import { PageHeader } from '../components/common/PageHeader'
import { Select } from '../components/common/Select'
import type { AdStructure, CatalogImport, City } from '../types'

function errorMessage(reason: unknown): string {
  return reason instanceof Error ? reason.message : String(reason)
}

// Пауза перед запросом по набранному в поиске. Без неё каждое нажатие клавиши
// уходило в базу: «Ленина» — это шесть запросов подряд, пять из которых
// устаревают, не успев вернуться.
const SEARCH_DELAY_MS = 300

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
  // null — список городов ещё не пришёл. Отличать это от «городов нет» надо:
  // без города не запускается ни одна загрузка, и страница иначе висела бы на
  // «Загружаем…» вечно, ничего при этом не загружая.
  const [cities, setCities] = useState<City[] | null>(null)
  const [citySlug, setCitySlug] = useState('')
  const [search, setSearch] = useState('')
  // Что реально ушло в запрос: `search` меняется на каждую букву, это — с паузой.
  const [searchQuery, setSearchQuery] = useState('')
  const [error, setError] = useState<string | null>(null)

  // Загруженное храним с меткой, чьего оно города: между сменой города и ответом
  // сервера иначе показываются конструкции предыдущего. Метка — только город,
  // без строки поиска, и это намеренно: уточняя поиск, человек должен видеть
  // прежний результат, пока едет новый, а не пустую таблицу на каждой букве.
  const [loadedStructures, setLoadedStructures] = useState<{
    citySlug: string
    items: AdStructure[]
    total: number
  } | null>(null)
  const [loadedImports, setLoadedImports] = useState<{
    citySlug: string
    items: CatalogImport[]
  } | null>(null)

  useEffect(() => {
    getCities()
      .then((list) => {
        setCities(list)
        setCitySlug((current) => current || list[0]?.slug || '')
      })
      .catch((reason) => setError(errorMessage(reason)))
  }, [])

  useEffect(() => {
    const timer = setTimeout(() => setSearchQuery(search), SEARCH_DELAY_MS)
    return () => clearTimeout(timer)
  }, [search])

  // История ревизий зависит только от города. Раньше она ехала в одном
  // Promise.all с конструкциями и потому перезапрашивалась на каждую букву
  // поиска, хотя от текста поиска не меняется вовсе.
  useEffect(() => {
    if (!citySlug) return
    let disposed = false

    getCatalogImports(citySlug)
      .then((items) => {
        if (!disposed) setLoadedImports({ citySlug, items })
      })
      .catch((reason) => {
        if (!disposed) setError(errorMessage(reason))
      })

    return () => {
      disposed = true
    }
  }, [citySlug])

  useEffect(() => {
    if (!citySlug) return
    let disposed = false

    getAdStructures(citySlug, { search: searchQuery || undefined })
      .then((page) => {
        if (disposed) return
        setLoadedStructures({ citySlug, items: page.items, total: page.total })
      })
      .catch((reason) => {
        if (!disposed) setError(errorMessage(reason))
      })

    return () => {
      disposed = true
    }
  }, [citySlug, searchQuery])

  // Выводим, а не сбрасываем в эффекте — как маршруты в VideosPage.
  const structuresOfCity =
    loadedStructures?.citySlug === citySlug ? loadedStructures : null
  const importsOfCity = loadedImports?.citySlug === citySlug ? loadedImports : null

  const structures = structuresOfCity?.items ?? []
  const total = structuresOfCity?.total ?? 0
  const currentRevision = importsOfCity?.items.find((item) => item.is_current)

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
            options={
              cities?.map((city) => ({ value: city.slug, label: city.name })) ?? []
            }
            onChange={setCitySlug}
          />
        </div>
        <p className="catalog-state">
          {/* Пока не пришли обе половины, честнее молчать: «Каталог пуст» на
              полсекунды при каждой смене города — это неправда, а не задержка. */}
          {!importsOfCity || !structuresOfCity
            ? 'Загружаем…'
            : currentRevision
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
        {cities !== null && cities.length === 0 ? (
          <EmptyState text="Городов пока нет. Город заводится в админ-панели." />
        ) : !structuresOfCity ? (
          <EmptyState text="Загружаем конструкции…" />
        ) : structures.length === 0 ? (
          <EmptyState
            text={
              searchQuery
                ? 'По этому адресу ничего не нашлось.'
                : 'Каталог пуст. Пак файлов загружается в админ-панели.'
            }
          />
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
