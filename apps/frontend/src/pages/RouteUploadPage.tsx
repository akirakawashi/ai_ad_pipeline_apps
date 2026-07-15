import { useState } from 'react'
import { completeUpload, createRun, uploadVideo } from '../api'
import { ErrorBanner } from '../components/common/Feedback'
import { PageHeader } from '../components/common/PageHeader'
import { ProgressBar } from '../components/common/ProgressBar'
import { findCity } from '../data/cities'
import { findRoute } from '../data/routes'
import { navigate } from '../routing'
import { formatBytes } from '../utils/formatters'

const MAX_FILES = 10

type ItemStatus = 'queued' | 'uploading' | 'done' | 'error'

interface UploadItem {
  key: string
  file: File
  status: ItemStatus
  progress: number
  error?: string
}

function makeKey(file: File) {
  return `${file.name}-${file.size}-${file.lastModified}`
}

export function RouteUploadPage({ cityId, routeId }: { cityId: string; routeId: string }) {
  const city = findCity(cityId)
  const route = findRoute(cityId, routeId)

  const [items, setItems] = useState<UploadItem[]>([])
  const [busy, setBusy] = useState(false)
  const [limitNotice, setLimitNotice] = useState<string | null>(null)

  const addFiles = (fileList: FileList | null) => {
    if (!fileList || busy) return
    const incoming = Array.from(fileList).map((file) => ({
      key: makeKey(file),
      file,
      status: 'queued' as ItemStatus,
      progress: 0,
    }))

    setItems((current) => {
      const existingKeys = new Set(current.map((item) => item.key))
      const deduped = incoming.filter((item) => !existingKeys.has(item.key))
      const room = MAX_FILES - current.length
      const accepted = deduped.slice(0, Math.max(room, 0))
      setLimitNotice(
        deduped.length > accepted.length
          ? `Можно загрузить не более ${MAX_FILES} видео за раз. Лишние файлы не добавлены.`
          : null,
      )
      return [...current, ...accepted]
    })
  }

  const removeItem = (key: string) => {
    if (busy) return
    setItems((current) => current.filter((item) => item.key !== key))
  }

  const startUpload = async () => {
    if (!items.length) return
    setBusy(true)

    for (const item of items) {
      if (item.status === 'done') continue
      setItems((current) =>
        current.map((entry) => (entry.key === item.key ? { ...entry, status: 'uploading', progress: 0 } : entry)),
      )
      try {
        const run = await createRun(item.file)
        await uploadVideo(run.upload, item.file, (progress) => {
          setItems((current) =>
            current.map((entry) => (entry.key === item.key ? { ...entry, progress } : entry)),
          )
        })
        await completeUpload(run.run_id)
        setItems((current) =>
          current.map((entry) => (entry.key === item.key ? { ...entry, status: 'done', progress: 100 } : entry)),
        )
      } catch (reason) {
        const message = reason instanceof Error ? reason.message : String(reason)
        setItems((current) =>
          current.map((entry) => (entry.key === item.key ? { ...entry, status: 'error', error: message } : entry)),
        )
      }
    }

    setBusy(false)
  }

  if (!city || !route) {
    return (
      <div className="page narrow-page">
        <PageHeader eyebrow="Маршруты" title="Маршрут не найден" />
        <ErrorBanner text="Проверьте ссылку или выберите маршрут заново." />
        <button className="secondary" style={{ marginTop: 16 }} onClick={() => navigate('/routes')}>
          К выбору города
        </button>
      </div>
    )
  }

  const doneCount = items.filter((item) => item.status === 'done').length
  const canStart = items.length > 0 && !busy && items.some((item) => item.status !== 'done')
  const allDone = items.length > 0 && doneCount === items.length

  return (
    <div className="page narrow-page">
      <PageHeader
        eyebrow={`${city.name} · ${route.name}`}
        title="Загрузите видео маршрута"
        description={`До ${MAX_FILES} роликов за раз. Файлы загружаются в хранилище — обработка подключится позже.`}
        actions={
          <button className="secondary" onClick={() => navigate(`/routes/${cityId}`)}>
            К маршруту
          </button>
        }
      />

      <section
        className={`upload-panel${busy ? ' busy' : ''}`}
        onDragEnter={(event) => event.preventDefault()}
        onDragOver={(event) => event.preventDefault()}
        onDrop={(event) => {
          event.preventDefault()
          addFiles(event.dataTransfer.files)
        }}
      >
        <div className="upload-icon">↑</div>
        <h2>{items.length ? `Выбрано видео: ${items.length}` : 'Перетащите видео сюда'}</h2>
        <p>
          {items.length
            ? 'Можно добавить ещё или начать загрузку.'
            : 'Подойдут MP4, MOV, MKV и WebM'}
        </p>

        <div className="upload-actions">
          <label className="secondary file-button">
            Добавить видео
            <input
              type="file"
              accept="video/*,.mkv"
              multiple
              disabled={busy || items.length >= MAX_FILES}
              onChange={(event) => {
                addFiles(event.target.files)
                event.target.value = ''
              }}
            />
          </label>
        </div>

        {limitNotice && <ErrorBanner text={limitNotice} />}

        {items.length > 0 && (
          <div className="upload-batch-list">
            {items.map((item) => (
              <div className="file-card upload-batch-item" key={item.key}>
                <div className="file-card-icon">▶</div>
                <div>
                  <strong>{item.file.name}</strong>
                  <span>{formatBytes(item.file.size)}</span>
                  {item.status === 'uploading' && (
                    <ProgressBar progress={item.progress} label="Загружается" animated />
                  )}
                  {item.status === 'error' && <span className="upload-batch-error">{item.error}</span>}
                </div>
                <div className={`status status-${item.status === 'done' ? 'completed' : item.status === 'error' ? 'processing_failed' : item.status === 'uploading' ? 'processing' : 'queued'}`}>
                  {item.status === 'queued' && 'В очереди'}
                  {item.status === 'uploading' && `${item.progress}%`}
                  {item.status === 'done' && 'Загружено'}
                  {item.status === 'error' && 'Ошибка'}
                </div>
                {!busy && item.status !== 'done' && (
                  <button className="ghost-button" onClick={() => removeItem(item.key)}>
                    Убрать
                  </button>
                )}
              </div>
            ))}
          </div>
        )}

        {items.length > 0 && (
          <p className="upload-batch-summary">
            Загружено {doneCount} из {items.length}
          </p>
        )}

        {allDone && (
          <button className="secondary action-button" onClick={() => navigate('/runs')}>
            Открыть архив
          </button>
        )}

        <button
          className="primary action-button"
          disabled={!canStart}
          onClick={() => void startUpload()}
        >
          {busy ? 'Загружаем…' : 'Начать загрузку'}
        </button>
      </section>
    </div>
  )
}
