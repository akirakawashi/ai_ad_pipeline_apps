import { ErrorBanner } from '../components/common/Feedback'
import {
  AnimatedDots,
  InfinityLoader,
} from '../components/common/LoadingIndicators'
import { PageHeader } from '../components/common/PageHeader'
import { PipelineSteps } from '../components/common/PipelineSteps'
import { ProgressBar } from '../components/common/ProgressBar'
import { stageDescription, stageLabel } from '../pipeline'
import { navigate } from '../routing'
import type { PipelineRun } from '../types'

export function ProcessingPage({ run }: { run: PipelineRun }) {
  const failed = run.status === 'processing_failed'
  return (
    <div className="page narrow-page">
      <PageHeader
        eyebrow={failed ? 'Обработка не прошла' : 'Видео обрабатывается'}
        title={run.source_name}
        description={run.status_message ?? 'Ждём первый статус от обработчика'}
        actions={
          <div className="page-actions">
            <button className="secondary" onClick={() => navigate('/videos')}>
              Все видео
            </button>
            <button className="primary" onClick={() => navigate('/upload')}>
              Добавить видео
            </button>
          </div>
        }
      />
      <section className={`processing-panel${failed ? ' failed' : ''}`}>
        <div className="processing-hero">
          <InfinityLoader />
          <div>
            <div className="progress-number">{run.progress}%</div>
            <div className="processing-now">
              <strong>
                {stageLabel(run.stage)}
                {!failed && <AnimatedDots />}
              </strong>
              <p>{stageDescription(run.stage)}</p>
            </div>
          </div>
        </div>
        <ProgressBar
          progress={run.progress}
          label={stageLabel(run.stage)}
          animated={!failed}
        />
        <PipelineSteps activeStage={run.stage} failed={failed} />
        {failed && (
          <ErrorBanner
            text={run.error_message ?? 'Анализ остановился с ошибкой'}
          />
        )}
      </section>
    </div>
  )
}
