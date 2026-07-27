import { useEffect, useRef, useState } from 'react'
import {
  applyCatalogImport,
  deleteCatalogImport,
  getAdStructures,
  getCatalogImports,
  getCities,
  restoreCatalogImport,
  uploadCatalogImport,
} from '../api'
import { EmptyState, ErrorBanner } from '../components/common/Feedback'
import { PageHeader } from '../components/common/PageHeader'
import { Select } from '../components/common/Select'
import { UserSelect } from '../components/common/UserSelect'
import type { AdStructure, CatalogImport, CatalogImportReport, City } from '../types'

const ACCEPTED = '.xlsx,.xls,.csv'
const MAX_FILES = 20

function errorMessage(reason: unknown): string {
  return reason instanceof Error ? reason.message : String(reason)
}

function formatMoment(value: string | null): string {
  if (!value) return '—'
  return new Date(value).toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function Metric({
  label,
  value,
  note,
}: {
  label: string
  value: string
  note?: string
}) {
  return (
    <div className="catalog-metric">
      <span className="catalog-metric-label">{label}</span>
      <strong>{value}</strong>
      {note && <span className="catalog-metric-note">{note}</span>}
    </div>
  )
}

/**
 * Каталог рекламных конструкций города.
 *
 * Пак файлов сначала только разбирается: человек видит отчёт и решает,
 * применять или нет. До применения каталог не меняется ни на одну точку —
 * поэтому «−180 точек» в отчёте важнее всех остальных цифр, неполный файл
 * выглядит именно так.
 */
export function CatalogPage() {
  const [cities, setCities] = useState<City[]>([])
  const [citySlug, setCitySlug] = useState('')
  const [structures, setStructures] = useState<AdStructure[]>([])
  const [total, setTotal] = useState(0)
  const [imports, setImports] = useState<CatalogImport[]>([])
  const [search, setSearch] = useState('')
  const [uploaderId, setUploaderId] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [report, setReport] = useState<CatalogImportReport | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)

  // Счётчик перезагрузок: действия над ревизиями меняют данные на сервере, и
  // экран должен перечитать их тем же путём, что и при смене города.
  const [version, setVersion] = useState(0)
  const reload = () => setVersion((current) => current + 1)

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
  }, [citySlug, search, version])

  const currentRevision = imports.find((item) => item.is_current)

  const resetSelection = () => {
    setFiles([])
    if (fileInput.current) fileInput.current.value = ''
  }

  const handleUpload = async () => {
    if (!files.length || !uploaderId) return
    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      setReport(await uploadCatalogImport(citySlug, files, uploaderId))
    } catch (reason) {
      setError(errorMessage(reason))
    } finally {
      setBusy(false)
    }
  }

  const finishImport = async (action: 'apply' | 'cancel') => {
    if (!report) return
    setBusy(true)
    setError(null)
    try {
      if (action === 'apply') {
        const applied = await applyCatalogImport(report.catalog_import.id)
        setNotice(`Применена ревизия ${applied.revision}.`)
      } else {
        await deleteCatalogImport(report.catalog_import.id)
        setNotice('Загрузка отменена, каталог не изменился.')
      }
      setReport(null)
      resetSelection()
      reload()
    } catch (reason) {
      setError(errorMessage(reason))
    } finally {
      setBusy(false)
    }
  }

  const handleRestore = async (item: CatalogImport) => {
    setBusy(true)
    setError(null)
    try {
      await restoreCatalogImport(item.id)
      setNotice(`Возвращена ревизия ${item.revision}.`)
      reload()
    } catch (reason) {
      setError(errorMessage(reason))
    } finally {
      setBusy(false)
    }
  }

  const handleDelete = async (item: CatalogImport) => {
    setBusy(true)
    setError(null)
    try {
      await deleteCatalogImport(item.id)
      reload()
    } catch (reason) {
      setError(errorMessage(reason))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="page">
      <PageHeader
        eyebrow="Каталог"
        title="Рекламные конструкции"
        description="Загружается паком файлов на город. Новый пак заменяет прежний целиком."
      />

      {error && <ErrorBanner text={error} />}

      <section className="filter-bar">
        <div className="field">
          Город
          <Select
            ariaLabel="Город"
            value={citySlug}
            options={cities.map((city) => ({ value: city.slug, label: city.name }))}
            onChange={(slug) => {
              setCitySlug(slug)
              setReport(null)
              resetSelection()
            }}
          />
        </div>
        <p className="catalog-state">
          {currentRevision
            ? `Ревизия ${currentRevision.revision} · точек: ${total}`
            : 'Каталог пуст'}
        </p>
      </section>

      {notice && <p className="catalog-hint">{notice}</p>}

      <section className="panel catalog-panel">
        <h2>Загрузка пака</h2>
        <p className="catalog-hint">
          До {MAX_FILES} файлов формата xlsx, xls или csv — все по одному городу.
          Файлы разбираются и не сохраняются: в базу уезжают только данные.
        </p>

        <div className="catalog-row">
          <div className="field">
            Файлы
            <label className="secondary file-button">
              Выбрать файлы
              <input
                ref={fileInput}
                type="file"
                accept={ACCEPTED}
                multiple
                disabled={busy}
                onChange={(event) =>
                  setFiles(Array.from(event.target.files ?? []).slice(0, MAX_FILES))
                }
              />
            </label>
          </div>
          <UserSelect
            label="Кто загрузил"
            value={uploaderId}
            onChange={setUploaderId}
            disabled={busy}
          />
          <button
            className="primary action-button"
            disabled={busy || !files.length || !uploaderId}
            onClick={handleUpload}
          >
            Разобрать файлы
          </button>
        </div>

        {files.length > 0 && (
          <div className="catalog-files">
            <span className="catalog-hint">
              Выбрано файлов: {files.length} — {files.map((file) => file.name).join(', ')}
            </span>
            <button className="ghost-button" disabled={busy} onClick={resetSelection}>
              Очистить
            </button>
          </div>
        )}
      </section>

      {report && (
        <section className="panel catalog-panel">
          <h2>Что произойдёт</h2>
          <div className="catalog-metrics">
            <Metric
              label="Точек станет"
              value={`${report.points_after}`}
              note={`было ${report.points_before}`}
            />
            <Metric label="Появится" value={`+${report.added}`} />
            <Metric label="Исчезнет" value={`−${report.removed}`} />
            <Metric
              label="Строк схлопнуто"
              value={`${report.collapsed_rows}`}
              note={`прочитано ${report.catalog_import.rows_read}`}
            />
            <Metric
              label="Строк отброшено"
              value={`${report.catalog_import.rows_rejected}`}
            />
          </div>

          {report.rejected_files.length > 0 && (
            <div className="catalog-issues">
              <h3>Файлы отклонены целиком</h3>
              <ul>
                {report.rejected_files.map((file) => (
                  <li key={file.file_name}>
                    {file.file_name} — {file.reason}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {report.files_with_extra_sheets.length > 0 && (
            <p className="catalog-hint">
              Лишние листы, читаем только первый:{' '}
              {report.files_with_extra_sheets.join(', ')}
            </p>
          )}

          {report.row_errors.length > 0 && (
            <details className="catalog-issues">
              <summary>Пропущенные строки: {report.row_errors.length}</summary>
              <ul>
                {report.row_errors.slice(0, 50).map((row, index) => (
                  <li key={index}>
                    {row.file_name}, строка {row.row_number} — {row.reason}
                  </li>
                ))}
              </ul>
            </details>
          )}

          <div className="catalog-row">
            <button
              className="primary action-button"
              disabled={busy}
              onClick={() => finishImport('apply')}
            >
              Применить
            </button>
            <button
              className="secondary action-button"
              disabled={busy}
              onClick={() => finishImport('cancel')}
            >
              Отменить
            </button>
          </div>
        </section>
      )}

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
          <EmptyState text="Пока пусто. Загрузите пак файлов." />
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

      <section className="panel catalog-panel">
        <h2>История ревизий</h2>
        {imports.length === 0 ? (
          <EmptyState text="Загрузок ещё не было." />
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Ревизия</th>
                  <th>Когда</th>
                  <th>Кто загрузил</th>
                  <th>Файлы</th>
                  <th className="numeric">Точек</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {imports.map((item) => (
                  <tr key={item.id} className={item.is_current ? 'is-current' : ''}>
                    <td>{item.revision ?? 'не применена'}</td>
                    <td>{formatMoment(item.applied_at ?? item.created_at)}</td>
                    <td>{item.uploaded_by?.full_name ?? '—'}</td>
                    <td>{item.file_names.join(', ')}</td>
                    <td className="numeric">{item.points_total}</td>
                    <td>
                      {item.is_current ? (
                        <span className="catalog-badge">показывается</span>
                      ) : (
                        <span className="row-actions">
                          {item.revision !== null && (
                            <button
                              className="ghost-button"
                              disabled={busy}
                              onClick={() => handleRestore(item)}
                            >
                              Вернуть
                            </button>
                          )}
                          <button
                            className="ghost-button"
                            disabled={busy}
                            onClick={() => handleDelete(item)}
                          >
                            Удалить
                          </button>
                        </span>
                      )}
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
