import { useEffect, useState } from 'react'
import { getAssignment, getCities, getCity, getRouteAssignments } from '../api'
import { DateField } from '../components/common/DateField'
import { FileCard } from '../components/common/FileCard'
import { ErrorBanner, InfoBanner } from '../components/common/Feedback'
import { PageHeader } from '../components/common/PageHeader'
import { ProgressBar } from '../components/common/ProgressBar'
import { Select } from '../components/common/Select'
import { UserSelect } from '../components/common/UserSelect'
import { useVideoUpload } from '../hooks/useVideoUpload'
import { assignmentPath, navigate } from '../routing'
import type { Assignment, City, CityDetail } from '../types'

const MAX_FILES = 20

const STATUS_CLASS: Record<string, string> = {
  queued: 'queued',
  uploading: 'processing',
  done: 'completed',
  error: 'processing_failed',
}

const STATUS_TEXT: Record<string, string> = {
  queued: 'В очереди',
  done: 'Загружено',
  error: 'Ошибка',
}

interface UploadPageProps {
  citySlug?: string
  routeSlug?: string
  /** Догрузка в конкретное задание: назначение зафиксировано. */
  assignmentId?: string
}

export function UploadPage({ citySlug, routeSlug, assignmentId }: UploadPageProps) {
  const [cities, setCities] = useState<City[]>([])
  const [detail, setDetail] = useState<CityDetail | null>(null)
  // Задания храним вместе с меткой, чьи они, — как маршруты в VideosPage.
  // Без метки список пережил бы смену города и выдал бы себя за задания нового.
  const [loadedAssignments, setLoadedAssignments] = useState<{
    routeKey: string
    items: Assignment[]
  } | null>(null)
  const [pinnedAssignment, setPinnedAssignment] = useState<Assignment | null>(null)
  const [selectedCity, setSelectedCity] = useState(citySlug ?? '')
  const [selectedRoute, setSelectedRoute] = useState(routeSlug ?? '')
  const [selectedAssignment, setSelectedAssignment] = useState('')
  const [uploadedById, setUploadedById] = useState('')
  const [catalogError, setCatalogError] = useState<string | null>(null)

  const pinned = Boolean(assignmentId)

  useEffect(() => {
    if (!assignmentId) return
    getAssignment(assignmentId)
      .then(setPinnedAssignment)
      .catch((reason) => setCatalogError(String(reason)))
  }, [assignmentId])

  useEffect(() => {
    if (pinned) return
    getCities()
      .then(setCities)
      .catch((reason) => setCatalogError(String(reason)))
  }, [pinned])

  useEffect(() => {
    if (pinned || !selectedCity) return
    let disposed = false
    getCity(selectedCity)
      .then((result) => {
        if (disposed) return
        setDetail(result)
        setSelectedRoute((current) =>
          result.routes.some((route) => route.slug === current)
            ? current
            : (result.routes[0]?.slug ?? ''),
        )
      })
      .catch((reason) => {
        if (!disposed) setCatalogError(String(reason))
      })
    return () => {
      disposed = true
    }
  }, [pinned, selectedCity])

  useEffect(() => {
    if (pinned || !selectedCity || !selectedRoute) return
    const routeKey = `${selectedCity}/${selectedRoute}`
    let disposed = false
    getRouteAssignments(selectedCity, selectedRoute)
      .then((page) => {
        if (disposed) return
        setLoadedAssignments({ routeKey, items: page.items })
        // Список идёт от свежих: обычно грузят в последнее заведённое задание.
        setSelectedAssignment(page.items[0]?.id ?? '')
      })
      .catch((reason) => {
        if (!disposed) setCatalogError(String(reason))
      })
    return () => {
      disposed = true
    }
  }, [pinned, selectedCity, selectedRoute])

  // Выводим, а не сбрасываем в эффекте: пока грузится новый город, старый
  // список маршрутов не должен показываться как его.
  const activeDetail = detail && detail.slug === selectedCity ? detail : null

  // Тем же приёмом и задания. Метка обязательна: между сменой города и ответом
  // сервера страница показывает новый город, а список заданий ещё старый —
  // и в это окно можно было отправить съёмку в задание прежнего города.
  const routeKey = `${selectedCity}/${selectedRoute}`
  const assignmentsReady = loadedAssignments?.routeKey === routeKey
  const assignments =
    pinned || !selectedCity || !selectedRoute || !assignmentsReady
      ? []
      : (loadedAssignments?.items ?? [])

  // Выбранное задание тоже устаревает вместе со списком: сам по себе это просто
  // идентификатор, и он переживает смену города. Считаем его выбранным, только
  // пока он есть в текущем списке. В VideosPage такого нет — там выбор живёт в
  // адресе и устареть не может, здесь он в состоянии страницы.
  const activeAssignment = assignments.some((item) => item.id === selectedAssignment)
    ? selectedAssignment
    : ''

  // Задание обязательно: съёмки вне маршрута не бывает. Пока оно не выбрано,
  // грузить некуда — кнопка выключена, и это единственное состояние «не готов».
  //
  // В режиме догрузки берём идентификатор загруженного задания, а не тот, что
  // стоит в адресе. Разница видна, когда задание скрыли: ссылка из чужой
  // вкладки ещё жива, `getAssignment` уже отвечает 404, и по адресному id
  // кнопка осталась бы включённой — загрузка падала бы пофайлово на POST /runs
  // вместо честного «грузить некуда».
  const targetAssignmentId = pinned ? (pinnedAssignment?.id ?? '') : activeAssignment

  // Именно эта строка гасит «Загрузить» в окне рассинхрона: без неё выпадашка
  // была бы честной, а отправить в чужое задание всё равно можно.
  const destinationReady = Boolean(targetAssignmentId)
  const routeChosen = Boolean(selectedCity && selectedRoute)
  // Файлы выбирают только после реквизитов партии. Кроме честного порядка
  // действий это закрывает двусмысленное состояние: зелёная, но disabled
  // кнопка раньше выглядела как разрешение грузить без задания.
  const uploadReady = destinationReady && Boolean(uploadedById)
  const missingUploadFields: string[] = []
  if (!pinned && !selectedCity) missingUploadFields.push('город')
  if (!pinned && !selectedRoute) missingUploadFields.push('маршрут')
  if (!destinationReady) missingUploadFields.push('задание')
  if (!uploadedById) missingUploadFields.push('сотрудника')
  const missingUploadLabel =
    missingUploadFields.length > 1
      ? `${missingUploadFields.slice(0, -1).join(', ')} и ${
          missingUploadFields[missingUploadFields.length - 1]
        }`
      : missingUploadFields[0]

  const upload = useVideoUpload({
    maxFiles: MAX_FILES,
    assignmentId: targetAssignmentId,
    uploadedByUserId: uploadedById || null,
    onFinish: ({ failed }) => {
      // При частичном сбое остаёмся на странице: «Повторить» дольёт туда же.
      if (failed > 0) return
      // Уходим всегда в задание: другого места для съёмки теперь нет.
      navigate(assignmentPath(targetAssignmentId))
    },
  })

  const eyebrow = pinned
    ? (pinnedAssignment?.title ?? 'Догрузка в задание')
    : activeDetail && selectedRoute
      ? `${activeDetail.name} · ${
          activeDetail.routes.find((route) => route.slug === selectedRoute)?.name ?? ''
        }`
      : 'Загрузка'

  return (
    <div className="page narrow-page">
      <PageHeader
        eyebrow={eyebrow}
        title="Загрузка видео"
        description={`Видео попадут в выбранное задание. До ${MAX_FILES} штук.`}
      />

      {catalogError && <ErrorBanner text={catalogError} />}

      <section className="panel destination-panel">
        <h2>Куда загрузить?</h2>

        {!pinned && (
          <>
            <div className="destination-fields">
              <div className="field">
                Город
                <Select
                  ariaLabel="Город"
                  value={selectedCity}
                  disabled={upload.busy}
                  placeholder="Выберите город"
                  options={cities.map((city) => ({
                    value: city.slug,
                    label: city.name,
                  }))}
                  onChange={setSelectedCity}
                />
              </div>
              <div className="field">
                Маршрут
                <Select
                  ariaLabel="Маршрут"
                  value={selectedRoute}
                  disabled={!activeDetail || upload.busy}
                  placeholder={
                    activeDetail ? 'Выберите маршрут' : 'Сначала выберите город'
                  }
                  options={
                    activeDetail?.routes.map((route) => ({
                      value: route.slug,
                      label: route.name,
                    })) ?? []
                  }
                  onChange={setSelectedRoute}
                />
              </div>
              <div className="field">
                Задание
                <Select
                  ariaLabel="Задание"
                  value={activeAssignment}
                  disabled={!assignments.length || upload.busy}
                  placeholder={
                    !routeChosen
                      ? 'Сначала выберите маршрут'
                      : assignmentsReady
                        ? 'Заданий пока нет'
                        : 'Загружаем задания…'
                  }
                  options={assignments.map((assignment) => ({
                    value: assignment.id,
                    label: assignment.title,
                  }))}
                  onChange={setSelectedAssignment}
                />
              </div>
            </div>

            {/* assignmentsReady обязателен: без него баннер мигал бы «нет
                заданий» на каждой смене маршрута, пока список ещё грузится. */}
            {routeChosen && assignmentsReady && !assignments.length && (
              <InfoBanner text="На этом маршруте нет заданий. Заведите задание на странице маршрута: видео загружаются в готовое задание." />
            )}

          </>
        )}

        <div className="destination-fields">
          <UserSelect
            label="Кто загрузил"
            value={uploadedById}
            disabled={upload.busy}
            placeholder="Кто загрузил"
            onChange={setUploadedById}
          />
        </div>
      </section>

      {!uploadReady ? (
        <section className="upload-panel is-locked" aria-disabled="true">
          <span className="upload-lock-icon" aria-hidden="true" />
          <h2>Загрузка пока недоступна</h2>
          <p>Осталось выбрать: {missingUploadLabel}.</p>
          <span className="upload-lock-note">
            После этого откроются выбор файлов и перетаскивание.
          </span>
        </section>
      ) : (
        <section
          className={`upload-panel${upload.busy ? ' busy' : ''}${
            upload.dragActive ? ' drag-active' : ''
          }${upload.items.length ? ' has-files' : ''}`}
          {...upload.dragHandlers}
        >
          <div className="upload-icon">↑</div>
          <h2>
            {upload.items.length
              ? `Выбрано видео: ${upload.items.length} из ${MAX_FILES}`
              : 'Перетащите видео сюда'}
          </h2>
          <p>
            {upload.items.length
              ? 'Можно добавить ещё или начать загрузку.'
              : 'Подойдут MP4, MOV, MKV и WebM'}
          </p>

          <div className="upload-actions">
            <label className="secondary file-button">
              Выбрать файлы
              <input
                type="file"
                accept="video/*,.mkv"
                multiple
                disabled={upload.busy || upload.items.length >= MAX_FILES}
                onChange={(event) => {
                  upload.addFiles(event.target.files)
                  event.target.value = ''
                }}
              />
            </label>
          </div>

          {upload.limitNotice && <InfoBanner text={upload.limitNotice} />}
          {upload.error && <ErrorBanner text={upload.error} />}

          {upload.items.length > 0 && (
            <div className="upload-file-list">
              {upload.items.map((item) => (
                <FileCard
                  key={item.key}
                  file={item.file}
                  status={
                    <div className={`status status-${STATUS_CLASS[item.status]}`}>
                      {item.status === 'uploading'
                        ? `${item.progress}%`
                        : STATUS_TEXT[item.status]}
                    </div>
                  }
                  actions={
                    !upload.busy && item.status !== 'done' ? (
                      <button
                        className="ghost-button"
                        onClick={() => upload.removeItem(item.key)}
                      >
                        Убрать
                      </button>
                    ) : undefined
                  }
                >
                  {/* Дата у каждого файла своя: одна съёмка — один проезд, и
                      партию нередко забирают с карты за несколько дней.
                      Автоподстановки нет: метка файла после копирования не
                      доказывает, когда видео действительно сняли. */}
                  <div className="upload-file-date">
                    <span>
                      Когда снято <b aria-hidden="true">*</b>
                    </span>
                    <DateField
                      value={item.shotDate}
                      required
                      invalid={!item.shotDate}
                      clearable={false}
                      placeholder="ДД.ММ.ГГГГ"
                      ariaLabel={`Когда снято: ${item.file.name}`}
                      disabled={upload.busy || item.status === 'done'}
                      onChange={(value) => upload.setShotDate(item.key, value)}
                    />
                  </div>
                  {!item.shotDate && (
                    <span className="upload-file-error">Укажите дату записи.</span>
                  )}
                  {item.status === 'uploading' && (
                    <ProgressBar
                      progress={item.progress}
                      label="Загружается"
                      animated
                    />
                  )}
                  {item.status === 'error' && (
                    <span className="upload-file-error">{item.error}</span>
                  )}
                </FileCard>
              ))}
            </div>
          )}

          {upload.items.length > 0 && (
            <p className="upload-file-summary">
              Загружено {upload.doneCount} из {upload.items.length}
            </p>
          )}

          {upload.failedCount > 0 && !upload.busy && (
            <button
              className="secondary action-button"
              disabled={!upload.datesReady}
              onClick={upload.retryFailed}
            >
              Повторить ({upload.failedCount})
            </button>
          )}

          <button
            className="primary action-button"
            disabled={!upload.canStart || !uploadReady}
            onClick={upload.start}
          >
            {upload.busy ? 'Загружаем…' : 'Начать загрузку'}
          </button>
        </section>
      )}
    </div>
  )
}
