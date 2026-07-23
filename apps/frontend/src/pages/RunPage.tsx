import { useEffect, useState } from 'react'
import { getRun } from '../api'
import { ErrorBanner, EmptyState } from '../components/common/Feedback'
import type { PipelineRun } from '../types'
import { ProcessingPage } from './ProcessingPage'
import { ResultPage } from './ResultPage'

export function RunPage({ runId, seek }: { runId: string; seek?: number }) {
  const [run, setRun] = useState<PipelineRun | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let disposed = false
    let timer = 0
    const load = async () => {
      try {
        const value = await getRun(runId)
        if (disposed) return
        setRun(value)
        if (!['completed', 'processing_failed'].includes(value.status)) {
          timer = window.setTimeout(load, 1500)
        }
      } catch (reason) {
        if (!disposed) setError(String(reason))
      }
    }
    void load()
    return () => {
      disposed = true
      window.clearTimeout(timer)
    }
  }, [runId])

  if (error) return <ErrorBanner text={error} />
  if (!run) return <EmptyState text="Открываем анализ…" />
  if (run.status !== 'completed') return <ProcessingPage run={run} />
  return <ResultPage run={run} initialSeek={seek} onRunUpdated={setRun} />
}
