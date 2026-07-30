import { useCallback, useRef, useState, type DragEvent } from 'react'
import { completeUpload, createRun, uploadVideo } from '../api'
import { isoFromDateInput } from '../utils/formatters'

export type UploadItemStatus = 'queued' | 'uploading' | 'done' | 'error'

export interface UploadItem {
  key: string
  file: File
  /**
   * Когда снимали, «ГГГГ-ММ-ДД». У каждого файла своя: партия из двадцати
   * видео — это, как правило, двадцать разных проездов, иногда в разные дни,
   * а график маршрута строится именно по этой дате. Общее на партию поле
   * проставило бы всем одинаковую и молча свело бы проезды в одну точку.
   */
  shotDate: string
  status: UploadItemStatus
  progress: number
  error?: string
  runId?: string
}

/**
 * Что уходит на сервер как время съёмки.
 *
 * Дату человек обязательно ставит сам для каждого файла. Время из файла не
 * используем: `lastModified` после переноса с карты памяти может быть временем
 * копирования. Поля времени в форме нет, поэтому отправляем начало выбранного
 * дня в локальном часовом поясе.
 */
function shotStartedAt(item: UploadItem): string {
  const fromInput = isoFromDateInput(item.shotDate)
  if (!fromInput) throw new Error('Укажите дату съёмки.')
  return fromInput
}

export interface UploadResult {
  runIds: string[]
  failed: number
}

export interface UseVideoUploadOptions {
  maxFiles: number
  /**
   * Задание, в которое кладём съёмки. Обязательно: съёмок вне маршрута нет.
   *
   * Задание создаётся заранее, в форме на странице маршрута: съёмка
   * подгружается в готовое задание, а не рождает его по ходу загрузки.
   * Поэтому ретраю упавших файлов не нужен ref — id задания неизменен.
   */
  assignmentId: string
  /** Оператор — один на всю партию: снимал её один человек. */
  operatorUserId: string | null
  onFinish?: (result: UploadResult) => void
}

function makeKey(file: File) {
  return `${file.name}-${file.size}-${file.lastModified}`
}

export function useVideoUpload({
  maxFiles,
  assignmentId,
  operatorUserId,
  onFinish,
}: UseVideoUploadOptions) {
  const [items, setItems] = useState<UploadItem[]>([])
  const [busy, setBusy] = useState(false)
  const [dragActive, setDragActive] = useState(false)
  const [limitNotice, setLimitNotice] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const dragDepth = useRef(0)

  const patch = useCallback((key: string, changes: Partial<UploadItem>) => {
    setItems((current) =>
      current.map((item) => (item.key === key ? { ...item, ...changes } : item)),
    )
  }, [])

  const addFiles = useCallback(
    (fileList: FileList | null) => {
      if (!fileList || busy) return
      const incoming = Array.from(fileList).map((file) => ({
        key: makeKey(file),
        file,
        shotDate: '',
        status: 'queued' as UploadItemStatus,
        progress: 0,
      }))

      setItems((current) => {
        const existing = new Set(current.map((item) => item.key))
        const deduped = incoming.filter((item) => !existing.has(item.key))
        const room = Math.max(maxFiles - current.length, 0)
        const accepted = deduped.slice(0, room)
        setLimitNotice(
          deduped.length > accepted.length
            ? maxFiles === 1
              ? 'Можно загрузить только одно видео.'
              : `Можно загрузить не более ${maxFiles} видео. Лишние файлы не добавлены.`
            : null,
        )
        return [...current, ...accepted]
      })
    },
    [busy, maxFiles],
  )

  const removeItem = useCallback(
    (key: string) => {
      if (busy) return
      setItems((current) => current.filter((item) => item.key !== key))
      setLimitNotice(null)
    },
    [busy],
  )

  const setShotDate = useCallback(
    (key: string, value: string) => {
      if (busy) return
      patch(key, { shotDate: value })
    },
    [busy, patch],
  )

  const clearAll = useCallback(() => {
    if (busy) return
    setItems([])
    setLimitNotice(null)
    setError(null)
  }, [busy])

  const runUpload = useCallback(
    async (queue: UploadItem[]) => {
      if (!queue.length) return
      setBusy(true)
      setError(null)

      const runIds: string[] = []
      let failed = 0

      for (const item of queue) {
        patch(item.key, { status: 'uploading', progress: 0, error: undefined })
        try {
          const run = await createRun(item.file, {
            assignmentId,
            operatorUserId,
            shotStartedAt: shotStartedAt(item),
          })
          await uploadVideo(run.upload, item.file, (progress) =>
            patch(item.key, { progress }),
          )
          await completeUpload(run.run_id)
          patch(item.key, { status: 'done', progress: 100, runId: run.run_id })
          runIds.push(run.run_id)
        } catch (reason) {
          failed += 1
          patch(item.key, {
            status: 'error',
            error: reason instanceof Error ? reason.message : String(reason),
          })
        }
      }

      setBusy(false)
      onFinish?.({ runIds, failed })
    },
    [assignmentId, onFinish, operatorUserId, patch],
  )

  const start = useCallback(() => {
    void runUpload(items.filter((item) => item.status !== 'done'))
  }, [items, runUpload])

  const retryFailed = useCallback(() => {
    void runUpload(items.filter((item) => item.status === 'error'))
  }, [items, runUpload])

  const dragHandlers = {
    onDragEnter: (event: DragEvent) => {
      event.preventDefault()
      dragDepth.current += 1
      if (!busy) setDragActive(true)
    },
    onDragOver: (event: DragEvent) => {
      event.preventDefault()
    },
    onDragLeave: (event: DragEvent) => {
      event.preventDefault()
      dragDepth.current -= 1
      if (dragDepth.current <= 0) {
        dragDepth.current = 0
        setDragActive(false)
      }
    },
    onDrop: (event: DragEvent) => {
      event.preventDefault()
      dragDepth.current = 0
      setDragActive(false)
      addFiles(event.dataTransfer.files)
    },
  }

  const doneCount = items.filter((item) => item.status === 'done').length
  const failedCount = items.filter((item) => item.status === 'error').length
  const datesReady = items.every((item) => Boolean(item.shotDate))

  return {
    items,
    busy,
    dragActive,
    limitNotice,
    error,
    doneCount,
    failedCount,
    datesReady,
    canStart: items.length > 0 && datesReady && !busy && doneCount < items.length,
    addFiles,
    removeItem,
    setShotDate,
    clearAll,
    start,
    retryFailed,
    dragHandlers,
  }
}
