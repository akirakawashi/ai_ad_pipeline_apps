import { useEffect, useState } from 'react'
import {
  createCity,
  createRoute,
  forgetAdminSession,
  hasAdminSession,
  getCities,
  getCity,
  updateCity,
  updateRoute,
  uploadRoadsGeometry,
  uploadRouteGeometry,
} from '../api'
import { AdminLogin } from '../components/AdminLogin'
import { EmptyState, ErrorBanner } from '../components/common/Feedback'
import { PageHeader } from '../components/common/PageHeader'
import { Select } from '../components/common/Select'
import type { City, CityDetail, Route } from '../types'
import { pluralAssignments, pluralRoutes } from '../utils/formatters'

const GEOJSON_ACCEPT = '.geojson,.json,application/geo+json,application/json'

function errorMessage(reason: unknown): string {
  return reason instanceof Error ? reason.message : String(reason)
}

interface CityDraft {
  slug: string
  name: string
  region: string
}

interface RouteDraft {
  slug: string
  name: string
  color_label: string
  color_hex: string
  description: string
}

const EMPTY_CITY: CityDraft = { slug: '', name: '', region: '' }
const EMPTY_ROUTE: RouteDraft = {
  slug: '',
  name: '',
  color_label: '',
  color_hex: '#05c3a1',
  description: '',
}

/**
 * Справочники городов и маршрутов.
 *
 * До этой страницы город и маршрут можно было завести только миграцией, а
 * геометрия лежала файлами внутри фронтенда. Теперь геометрия в базе и
 * загружается файлом; маршрут без загруженной линии — законное состояние, на нём
 * уже можно завести задание и разметить зоны.
 *
 * Удаления города и маршрута нет вовсе — только «Скрыть» и «Показать». У города
 * каскад на маршруты, у маршрутов на задания и съёмки: снос утащил бы всю
 * историю. Скрытое видно **только на этой странице** — приглушённым и с
 * пометкой. В этом весь смысл: скрыть можно откуда угодно, а вернуть неоткуда,
 * если справочник прячет скрытое наравне с остальными экранами.
 */
export function AdminPage() {
  // Пароль проверяет бэкенд; здесь только выбор, что рисовать. Ошибка 401 в
  // любом запросе гасит сессию в api.ts, поэтому просроченный вход сам вернёт
  // форму — состояние синхронизируется через reload().
  const [signedIn, setSignedIn] = useState(hasAdminSession())
  const [cities, setCities] = useState<City[]>([])
  const [citySlug, setCitySlug] = useState('')
  const [detail, setDetail] = useState<CityDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const [cityDraft, setCityDraft] = useState<CityDraft>(EMPTY_CITY)
  const [routeDraft, setRouteDraft] = useState<RouteDraft>(EMPTY_ROUTE)
  const [editingRoute, setEditingRoute] = useState<string | null>(null)
  const [routeEdit, setRouteEdit] = useState<RouteDraft>(EMPTY_ROUTE)
  const [cityEdit, setCityEdit] = useState<CityDraft | null>(null)

  // Счётчик перезагрузок: правки меняют данные на сервере, и экран перечитывает
  // их тем же путём, что и при смене города.
  const [version, setVersion] = useState(0)
  const reload = () => setVersion((current) => current + 1)

  useEffect(() => {
    let disposed = false
    getCities(true)
      .then((list) => {
        if (disposed) return
        setCities(list)
        setCitySlug((current) => current || list[0]?.slug || '')
      })
      .catch((reason) => {
        if (disposed) return
        setSignedIn(hasAdminSession())
        setError(errorMessage(reason))
      })
    return () => {
      disposed = true
    }
  }, [version])

  useEffect(() => {
    if (!citySlug) return
    let disposed = false
    getCity(citySlug, true)
      .then((loaded) => !disposed && setDetail(loaded))
      .catch((reason) => {
        if (disposed) return
        setSignedIn(hasAdminSession())
        setError(errorMessage(reason))
      })
    return () => {
      disposed = true
    }
  }, [citySlug, version])

  /** Общая обёртка действий: гасим прошлую ошибку, показываем итог, перечитываем. */
  const run = async (action: () => Promise<string>) => {
    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      setNotice(await action())
      reload()
    } catch (reason) {
      // Пароль сменили на сервере — api.ts уже забыл сессию, возвращаем форму.
      setSignedIn(hasAdminSession())
      setError(errorMessage(reason))
    } finally {
      setBusy(false)
    }
  }

  const addCity = () =>
    run(async () => {
      const created = await createCity({
        slug: cityDraft.slug.trim(),
        name: cityDraft.name.trim(),
        region: cityDraft.region.trim() || null,
        display_order: cities.length + 1,
      })
      setCityDraft(EMPTY_CITY)
      setCitySlug(created.slug)
      return `Город «${created.name}» создан.`
    })

  const saveCity = () =>
    run(async () => {
      if (cityEdit === null) return ''
      const updated = await updateCity(citySlug, {
        name: cityEdit.name.trim(),
        region: cityEdit.region.trim() || null,
      })
      setCityEdit(null)
      return `Город «${updated.name}» сохранён.`
    })

  const toggleCity = (isActive: boolean) =>
    run(async () => {
      const updated = await updateCity(citySlug, { is_active: isActive })
      return isActive
        ? `Город «${updated.name}» снова доступен всем.`
        : `Город «${updated.name}» скрыт. Здесь он остался — вернуть можно кнопкой.`
    })

  const addRoute = () =>
    run(async () => {
      const created = await createRoute(citySlug, {
        slug: routeDraft.slug.trim(),
        name: routeDraft.name.trim(),
        color_label: routeDraft.color_label.trim() || null,
        color_hex: routeDraft.color_hex,
        description: routeDraft.description.trim() || null,
        display_order: (detail?.routes.length ?? 0) + 1,
      })
      setRouteDraft(EMPTY_ROUTE)
      return `Маршрут «${created.name}» создан. Осталось загрузить линию.`
    })

  const saveRoute = () =>
    run(async () => {
      if (editingRoute === null) return ''
      const updated = await updateRoute(citySlug, editingRoute, {
        name: routeEdit.name.trim(),
        color_label: routeEdit.color_label.trim() || null,
        color_hex: routeEdit.color_hex,
        description: routeEdit.description.trim() || null,
      })
      setEditingRoute(null)
      return `Маршрут «${updated.name}» сохранён.`
    })

  const toggleRoute = (route: Route) =>
    run(async () => {
      const updated = await updateRoute(citySlug, route.slug, {
        is_active: !route.is_active,
      })
      return updated.is_active
        ? `Маршрут «${updated.name}» снова доступен.`
        : `Маршрут «${updated.name}» скрыт, его задания и съёмки на месте.`
    })

  const uploadRoads = (file: File) =>
    run(async () => {
      const updated = await uploadRoadsGeometry(citySlug, file)
      return `Дорожный слой «${updated.name}» загружен, рамка города пересчитана.`
    })

  const uploadRoute = (route: Route, file: File) =>
    run(async () => {
      await uploadRouteGeometry(citySlug, route.slug, file)
      return `Линия маршрута «${route.name}» загружена.`
    })

  const startRouteEdit = (route: Route) => {
    setEditingRoute(route.slug)
    setRouteEdit({
      slug: route.slug,
      name: route.name,
      color_label: route.color_label ?? '',
      color_hex: route.color_hex ?? EMPTY_ROUTE.color_hex,
      description: route.description ?? '',
    })
  }

  if (!signedIn) {
    return <AdminLogin onSuccess={() => setSignedIn(true)} />
  }

  return (
    <div className="page">
      <PageHeader
        eyebrow="Админ-панель"
        title="Города и маршруты"
        description="Слаг задаётся один раз: он в адресе страницы. Геометрия загружается файлом geojson и хранится в базе."
      />

      {/* Кнопка закреплена в углу экрана, а не в потоке страницы: форма
          длинная, и выход должен быть под рукой на любой её высоте. */}
      <button
        className="ghost-button admin-signout"
        onClick={() => {
          forgetAdminSession()
          setSignedIn(false)
        }}
      >
        Выйти
      </button>

      {error && <ErrorBanner text={error} />}
      {notice && <p className="catalog-hint">{notice}</p>}

      <section className="panel catalog-panel">
        <h2>Новый город</h2>
        <div className="geozone-fields">
          <label className="field">
            Слаг
            <input
              className="text-input"
              placeholder="kerch"
              value={cityDraft.slug}
              disabled={busy}
              onChange={(event) =>
                setCityDraft({ ...cityDraft, slug: event.target.value })
              }
            />
          </label>
          <label className="field">
            Название
            <input
              className="text-input"
              placeholder="Керчь"
              value={cityDraft.name}
              disabled={busy}
              onChange={(event) =>
                setCityDraft({ ...cityDraft, name: event.target.value })
              }
            />
          </label>
          <label className="field">
            Регион
            <input
              className="text-input"
              placeholder="Республика Крым"
              value={cityDraft.region}
              disabled={busy}
              onChange={(event) =>
                setCityDraft({ ...cityDraft, region: event.target.value })
              }
            />
          </label>
        </div>
        <div className="geozone-form-actions">
          <button
            className="primary"
            disabled={busy || !cityDraft.slug.trim() || !cityDraft.name.trim()}
            onClick={addCity}
          >
            Создать город
          </button>
        </div>
      </section>

      <section className="filter-bar">
        <div className="field">
          Город
          <Select
            ariaLabel="Город"
            value={citySlug}
            options={cities.map((city) => ({
              value: city.slug,
              // Скрытые видны только здесь, поэтому подписываем прямо в списке:
              // иначе непонятно, почему города нет на остальных страницах.
              label: city.is_active ? city.name : `${city.name} — скрыт`,
            }))}
            onChange={(slug) => {
              setCitySlug(slug)
              setEditingRoute(null)
              setCityEdit(null)
            }}
          />
        </div>
        {detail && (
          <p className="catalog-state">
            {pluralRoutes(detail.route_count)} · {pluralAssignments(detail.assignment_count)}
            {detail.has_roads_geometry ? ' · дорожный слой есть' : ' · дорожного слоя нет'}
            {!detail.is_active && ' · город скрыт'}
          </p>
        )}
      </section>

      {detail === null ? (
        <EmptyState text="Выберите город или создайте первый." />
      ) : (
        <>
          <section className="panel catalog-panel">
            <h2>{detail.name}</h2>
            {cityEdit === null ? (
              <>
                <p className="catalog-hint">
                  Слаг: {detail.slug} · регион: {detail.region ?? '—'}
                </p>
                <div className="geozone-form-actions">
                  <button
                    className="secondary"
                    disabled={busy}
                    onClick={() =>
                      setCityEdit({
                        slug: detail.slug,
                        name: detail.name,
                        region: detail.region ?? '',
                      })
                    }
                  >
                    Правка
                  </button>
                  <label className="secondary file-button">
                    Загрузить дорожный слой
                    <input
                      type="file"
                      accept={GEOJSON_ACCEPT}
                      disabled={busy}
                      onChange={(event) => {
                        const file = event.target.files?.[0]
                        if (file) void uploadRoads(file)
                        event.target.value = ''
                      }}
                    />
                  </label>
                  {detail.is_active ? (
                    <button
                      className="geozone-delete"
                      disabled={busy}
                      onClick={() => void toggleCity(false)}
                    >
                      Скрыть город
                    </button>
                  ) : (
                    <button
                      className="primary"
                      disabled={busy}
                      onClick={() => void toggleCity(true)}
                    >
                      Показать город
                    </button>
                  )}
                </div>
                {!detail.is_active && (
                  <p className="catalog-hint">
                    Город скрыт: его не видно ни в архиве, ни при загрузке видео,
                    ни в каталоге. Здесь он остаётся всегда — удаления города нет,
                    иначе вместе с ним ушли бы его задания и съёмки.
                  </p>
                )}
                <p className="catalog-hint">
                  Дорожный слой задаёт рамку города: ею каталог конструкций
                  отсекает точки, попавшие из другого города. При загрузке слоя
                  рамка пересчитывается.
                </p>
              </>
            ) : (
              <>
                <div className="geozone-fields">
                  <label className="field">
                    Название
                    <input
                      className="text-input"
                      value={cityEdit.name}
                      disabled={busy}
                      onChange={(event) =>
                        setCityEdit({ ...cityEdit, name: event.target.value })
                      }
                    />
                  </label>
                  <label className="field">
                    Регион
                    <input
                      className="text-input"
                      value={cityEdit.region}
                      disabled={busy}
                      onChange={(event) =>
                        setCityEdit({ ...cityEdit, region: event.target.value })
                      }
                    />
                  </label>
                </div>
                <div className="geozone-form-actions">
                  <button className="primary" disabled={busy} onClick={saveCity}>
                    Сохранить
                  </button>
                  <button
                    className="ghost-button"
                    disabled={busy}
                    onClick={() => setCityEdit(null)}
                  >
                    Отмена
                  </button>
                </div>
              </>
            )}
          </section>

          <section className="panel catalog-panel">
            <h2>Новый маршрут</h2>
            <div className="geozone-fields">
              <label className="field">
                Слаг
                <input
                  className="text-input"
                  placeholder="route-1"
                  value={routeDraft.slug}
                  disabled={busy}
                  onChange={(event) =>
                    setRouteDraft({ ...routeDraft, slug: event.target.value })
                  }
                />
              </label>
              <label className="field">
                Название
                <input
                  className="text-input"
                  placeholder="Камышовое шоссе | Лабораторное шоссе"
                  value={routeDraft.name}
                  disabled={busy}
                  onChange={(event) =>
                    setRouteDraft({ ...routeDraft, name: event.target.value })
                  }
                />
              </label>
              <label className="field">
                Подпись цвета
                <input
                  className="text-input"
                  placeholder="Красная линия"
                  value={routeDraft.color_label}
                  disabled={busy}
                  onChange={(event) =>
                    setRouteDraft({ ...routeDraft, color_label: event.target.value })
                  }
                />
              </label>
              <label className="field">
                Цвет
                <input
                  className="text-input"
                  type="color"
                  value={routeDraft.color_hex}
                  disabled={busy}
                  onChange={(event) =>
                    setRouteDraft({ ...routeDraft, color_hex: event.target.value })
                  }
                />
              </label>
              <label className="field geozone-field-wide">
                Описание
                <textarea
                  className="text-input geozone-textarea"
                  rows={2}
                  value={routeDraft.description}
                  disabled={busy}
                  onChange={(event) =>
                    setRouteDraft({ ...routeDraft, description: event.target.value })
                  }
                />
              </label>
            </div>
            <div className="geozone-form-actions">
              <button
                className="primary"
                disabled={busy || !routeDraft.slug.trim() || !routeDraft.name.trim()}
                onClick={addRoute}
              >
                Создать маршрут
              </button>
            </div>
          </section>

          <section className="panel catalog-panel">
            <h2>Маршруты</h2>
            {detail.routes.length === 0 ? (
              <EmptyState text="У города нет маршрутов." />
            ) : (
              <ul className="geozone-list">
                {detail.routes.map((route) =>
                  route.slug === editingRoute ? (
                    <li key={route.id} className="geozone-row is-editing">
                      <div className="geozone-fields">
                        <label className="field">
                          Название
                          <input
                            className="text-input"
                            value={routeEdit.name}
                            disabled={busy}
                            onChange={(event) =>
                              setRouteEdit({ ...routeEdit, name: event.target.value })
                            }
                          />
                        </label>
                        <label className="field">
                          Подпись цвета
                          <input
                            className="text-input"
                            value={routeEdit.color_label}
                            disabled={busy}
                            onChange={(event) =>
                              setRouteEdit({
                                ...routeEdit,
                                color_label: event.target.value,
                              })
                            }
                          />
                        </label>
                        <label className="field">
                          Цвет
                          <input
                            className="text-input"
                            type="color"
                            value={routeEdit.color_hex}
                            disabled={busy}
                            onChange={(event) =>
                              setRouteEdit({
                                ...routeEdit,
                                color_hex: event.target.value,
                              })
                            }
                          />
                        </label>
                        <label className="field geozone-field-wide">
                          Описание
                          <textarea
                            className="text-input geozone-textarea"
                            rows={2}
                            value={routeEdit.description}
                            disabled={busy}
                            onChange={(event) =>
                              setRouteEdit({
                                ...routeEdit,
                                description: event.target.value,
                              })
                            }
                          />
                        </label>
                      </div>
                      <div className="geozone-form-actions">
                        <button className="primary" disabled={busy} onClick={saveRoute}>
                          Сохранить
                        </button>
                        <button
                          className="ghost-button"
                          disabled={busy}
                          onClick={() => setEditingRoute(null)}
                        >
                          Отмена
                        </button>
                      </div>
                    </li>
                  ) : (
                    <li
                      key={route.id}
                      className={`geozone-row${route.is_active ? '' : ' is-hidden-row'}`}
                    >
                      <span
                        className="geozone-swatch"
                        style={{ background: route.color_hex ?? 'var(--muted)' }}
                      />
                      <div className="geozone-row-copy">
                        <span className="geozone-row-name">
                          {route.name} <em>{route.slug}</em>
                        </span>
                        <span className="geozone-row-range">
                          {route.color_label ?? 'без подписи цвета'} ·{' '}
                          {pluralAssignments(route.assignment_count)} ·{' '}
                          {route.has_geometry ? 'линия загружена' : 'линии нет'}
                          {!route.is_active && ' · скрыт'}
                        </span>
                        {route.description && (
                          <p className="geozone-row-description">{route.description}</p>
                        )}
                      </div>
                      <span className="row-actions">
                        <button
                          className="ghost-button"
                          disabled={busy}
                          onClick={() => startRouteEdit(route)}
                        >
                          Правка
                        </button>
                        <label className="secondary file-button">
                          {route.has_geometry ? 'Заменить линию' : 'Загрузить линию'}
                          <input
                            type="file"
                            accept={GEOJSON_ACCEPT}
                            disabled={busy}
                            onChange={(event) => {
                              const file = event.target.files?.[0]
                              if (file) void uploadRoute(route, file)
                              event.target.value = ''
                            }}
                          />
                        </label>
                        <button
                          className={route.is_active ? 'geozone-delete' : 'primary'}
                          disabled={busy}
                          onClick={() => void toggleRoute(route)}
                        >
                          {route.is_active ? 'Скрыть' : 'Показать'}
                        </button>
                      </span>
                    </li>
                  ),
                )}
              </ul>
            )}
          </section>
        </>
      )}
    </div>
  )
}
