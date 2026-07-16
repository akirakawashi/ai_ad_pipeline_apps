import { useCallback, useRef, useState, type DragEvent } from 'react'
import { completeUpload, createRun, uploadVideo } from '../api'

export type UploadItemStatus = 'queued' | 'uploading' | 'done' | 'error'

export interface UploadItem {
  key: string
  file: File
  status: UploadItemStatus
  progress: number
  error?: string
  runId?: string
}

export interface UploadResult {
  batchId: string | null
  runIds: string[]
  failed: number
}

export interface UseVideoUploadOptions {
  maxFiles: number
  /**
   * Зовётся один раз перед первым файлом. null — «Без маршрута».
   * Лениво: пачка появляется, только если загрузку реально начали.
   */
  createBatch?: () => Promise<string | null>
  onFinish?: (result: UploadResult) => void
}

function makeKey(file: File) {
  return `${file.name}-${file.size}-${file.lastModified}`
}

export function useVideoUpload({
  maxFiles,
  createBatch,
  onFinish,
}: UseVideoUploadOptions) {
  const [items, setItems] = useState<UploadItem[]>([])
  const [busy, setBusy] = useState(false)
  const [dragActive, setDragActive] = useState(false)
  const [limitNotice, setLimitNotice] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [batchId, setBatchId] = useState<string | null>(null)
  // Держим id пачки и в ref: ретрай упавших должен попасть в ту же пачку,
  // а не родить фантомную следующую.
  const batchIdRef = useRef<string | null>(null)
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

      let currentBatchId = batchIdRef.current
      if (currentBatchId === null && createBatch) {
        try {
          currentBatchId = await createBatch()
          batchIdRef.current = currentBatchId
          setBatchId(currentBatchId)
        } catch (reason) {
          setError(reason instanceof Error ? reason.message : String(reason))
          setBusy(false)
          return
        }
      }

      const runIds: string[] = []
      let failed = 0

      for (const item of queue) {
        patch(item.key, { status: 'uploading', progress: 0, error: undefined })
        try {
          const run = await createRun(item.file, currentBatchId)
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
      onFinish?.({ batchId: currentBatchId, runIds, failed })
    },
    [createBatch, onFinish, patch],
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

  return {
    items,
    busy,
    dragActive,
    limitNotice,
    error,
    batchId,
    doneCount,
    failedCount,
    canStart: items.length > 0 && !busy && doneCount < items.length,
    addFiles,
    removeItem,
    clearAll,
    start,
    retryFailed,
    dragHandlers,
  }
}
