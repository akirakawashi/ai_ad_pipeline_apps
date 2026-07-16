import { useEffect, useMemo, useState } from 'react'
import { createBatch, getCities, getCity } from '../api'
import { FileCard } from '../components/common/FileCard'
import { ErrorBanner, InfoBanner } from '../components/common/Feedback'
import { PageHeader } from '../components/common/PageHeader'
import { ProgressBar } from '../components/common/ProgressBar'
import { useVideoUpload } from '../hooks/useVideoUpload'
import { navigate } from '../routing'
import type { City, CityDetail } from '../types'

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
  /** Догрузка в существующую пачку: назначение зафиксировано. */
  batchId?: string
}

export function UploadPage({ citySlug, routeSlug, batchId }: UploadPageProps) {
  const [cities, setCities] = useState<City[]>([])
  const [detail, setDetail] = useState<CityDetail | null>(null)
  const [selectedCity, setSelectedCity] = useState(citySlug ?? '')
  const [selectedRoute, setSelectedRoute] = useState(routeSlug ?? '')
  const [noRoute, setNoRoute] = useState(!citySlug && !batchId)
  const [catalogError, setCatalogError] = useState<string | null>(null)

  const pinned = Boolean(batchId)

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

  // Выводим, а не сбрасываем в эффекте: пока грузится новый город, старый
  // список маршрутов не должен показываться как его.
  const activeDetail = detail && detail.slug === selectedCity ? detail : null
  const destinationReady = pinned || noRoute || Boolean(selectedCity && selectedRoute)

  const upload = useVideoUpload({
    maxFiles: MAX_FILES,
    createBatch: useMemo(
      () => async () => {
        if (batchId) return batchId
        if (noRoute) return null
        const batch = await createBatch(selectedCity, selectedRoute)
        return batch.id
      },
      [batchId, noRoute, selectedCity, selectedRoute],
    ),
    onFinish: ({ batchId: finishedBatchId, runIds, failed }) => {
      // При частичном сбое остаёмся на странице: «Повторить» дольёт в ту же пачку.
      if (failed > 0) return
      if (finishedBatchId) {
        navigate(`/batches/${finishedBatchId}`)
      } else if (runIds.length === 1) {
        navigate(`/videos/${runIds[0]}`)
      } else if (runIds.length > 0) {
        navigate('/videos')
      }
    },
  })

  const eyebrow = pinned
    ? 'Догрузка в пачку'
    : noRoute
      ? 'Без маршрута'
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
        description={
          noRoute
            ? 'Разовая загрузка — видео уйдёт в обработку вне города и маршрута.'
            : `Видео попадут в одну пачку маршрута. До ${MAX_FILES} штук.`
        }
      />

      {catalogError && <ErrorBanner text={catalogError} />}

      {!pinned && (
        <section className="panel destination-panel">
          <h2>Куда загрузить?</h2>
          <div className="destination-fields">
            <label>
              Город
              <select
                value={selectedCity}
                disabled={noRoute || upload.busy}
                onChange={(event) => setSelectedCity(event.target.value)}
              >
                <option value="">Выберите город</option>
                {cities.map((city) => (
                  <option key={city.id} value={city.slug}>
                    {city.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Маршрут
              <select
                value={selectedRoute}
                disabled={noRoute || !activeDetail || upload.busy}
                onChange={(event) => setSelectedRoute(event.target.value)}
              >
                {!activeDetail && <option value="">Сначала выберите город</option>}
                {activeDetail?.routes.map((route) => (
                  <option key={route.id} value={route.slug}>
                    {route.name}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <label className="destination-toggle">
            <input
              type="checkbox"
              checked={noRoute}
              disabled={upload.busy}
              onChange={(event) => setNoRoute(event.target.checked)}
            />
            Без маршрута (разовая загрузка)
          </label>
        </section>
      )}

      <section
        className={`upload-panel${upload.busy ? ' busy' : ''}${
          upload.dragActive ? ' drag-active' : ''
        }`}
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
          <div className="upload-batch-list">
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
                {item.status === 'uploading' && (
                  <ProgressBar progress={item.progress} label="Загружается" animated />
                )}
                {item.status === 'error' && (
                  <span className="upload-batch-error">{item.error}</span>
                )}
              </FileCard>
            ))}
          </div>
        )}

        {upload.items.length > 0 && (
          <p className="upload-batch-summary">
            Загружено {upload.doneCount} из {upload.items.length}
          </p>
        )}

        {upload.failedCount > 0 && !upload.busy && (
          <button className="secondary action-button" onClick={upload.retryFailed}>
            Повторить ({upload.failedCount})
          </button>
        )}

        <button
          className="primary action-button"
          disabled={!upload.canStart || !destinationReady}
          onClick={upload.start}
        >
          {upload.busy ? 'Загружаем…' : 'Начать загрузку'}
        </button>

        {!destinationReady && upload.items.length > 0 && (
          <InfoBanner text="Выберите город и маршрут или отметьте «Без маршрута»." />
        )}
      </section>
    </div>
  )
}
