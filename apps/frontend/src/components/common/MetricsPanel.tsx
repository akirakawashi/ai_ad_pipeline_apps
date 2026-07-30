import type { ReactNode } from 'react'

import { AggregateToggle } from './AggregateToggle'
import type { Aggregate } from '../../types'

/**
 * Плитки сводки и переключатель оценки — одним блоком.
 *
 * Раздельными карточками они были случайно, а не по смыслу: тумблер выбирает,
 * как посчитаны цифры в плитках, и стоять он должен внутри той же рамки, а не
 * над ней.
 *
 * Подпись стоит вплотную к переключателю и называет **его**, а не плитки, и это
 * важно. Плитки разнородны: «заметность за съёмку» и «объектов за съёмку» —
 * величины на одну съёмку, и оценка их меняет; «съёмок» и «отснято» — итоги за
 * всё, и переключатель на них не влияет. Прежняя надпись «Показатели за съёмку»
 * стояла над всеми четырьмя и обещала про половину неправду.
 */
export function MetricsPanel({
  aggregate,
  onAggregateChange,
  children,
}: {
  aggregate: Aggregate
  onAggregateChange: (value: Aggregate) => void
  children: ReactNode
}) {
  return (
    <section className="metrics-panel">
      <header className="metrics-panel-head">
        <span>Оценка за съёмку</span>
        <AggregateToggle value={aggregate} onChange={onAggregateChange} />
      </header>
      <div className="metrics-panel-grid">{children}</div>
    </section>
  )
}
