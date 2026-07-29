import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import {
  tooltipCursor,
  tooltipItemStyle,
  tooltipLabelStyle,
  tooltipStyle,
} from './common/chartTooltip'
import type { RouteShootingMetrics } from '../types'
import { formatDateTime, formatDuration } from '../utils/formatters'

/** Цвета кампаний: маршрут смотрят целиком, и глазом надо отделять задания. */
const ASSIGNMENT_COLORS = [
  '#05c3a1',
  '#58a6ff',
  '#e7c84d',
  '#ff7a59',
  '#b78bff',
  '#7fd1a0',
]

function shortDate(value: string | null): string {
  if (!value) return '—'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return '—'
  return new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit',
    month: '2-digit',
  }).format(parsed)
}

/**
 * Заметность каждой съёмки маршрута по порядку съёмки.
 *
 * Столбец на видео, а не на задание: маршрут считается из съёмок напрямую, и
 * график показывает то же самое. Цвет — задание, поэтому видно и то, что
 * кампании разного размера, и то, как менялась заметность между ними.
 */
export function RouteShootingsChart({
  shootings,
}: {
  shootings: RouteShootingMetrics[]
}) {
  const assignmentIds = [
    ...new Set(shootings.map((item) => item.assignment.assignment_id)),
  ]
  const colorOf = (assignmentId: string): string =>
    ASSIGNMENT_COLORS[assignmentIds.indexOf(assignmentId) % ASSIGNMENT_COLORS.length]

  const rows = shootings.map((item) => ({
    run_id: item.run_id,
    label: shortDate(item.shot_started_at),
    visibility: Number(item.visibility_index.toFixed(1)),
    objects: item.objects_count,
    color: colorOf(item.assignment.assignment_id),
    assignment: item.assignment.title,
    source_name: item.source_name,
    moment: formatDateTime(item.shot_started_at),
    duration_label: formatDuration(item.duration_sec),
  }))

  return (
    <section className="panel chart-card wide-chart">
      <header>
        <h3>Заметность по съёмкам</h3>
        <p>
          Столбец — одно видео, по порядку съёмки. Цвет — задание, в которое оно
          входит.
        </p>
      </header>
      <ResponsiveContainer width="100%" height={320}>
        <BarChart data={rows}>
          <CartesianGrid stroke="rgba(255,255,255,.08)" vertical={false} />
          <XAxis dataKey="label" stroke="#8d9298" />
          <YAxis stroke="#8d9298" />
          <Tooltip
            contentStyle={tooltipStyle}
            cursor={tooltipCursor}
            itemStyle={tooltipItemStyle}
            labelStyle={tooltipLabelStyle}
            labelFormatter={(_, series) => {
              const row = series?.[0]?.payload
              return row ? `${row.assignment} · ${row.moment}` : ''
            }}
            formatter={(value, _name, series) => {
              const row = series?.payload
              return [
                `${value} · объектов ${row?.objects} · ${row?.duration_label}`,
                'Заметность',
              ]
            }}
          />
          <Bar dataKey="visibility" name="Заметность" radius={[6, 6, 0, 0]}>
            {rows.map((row) => (
              <Cell key={row.run_id} fill={row.color} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <ul className="route-legend">
        {assignmentIds.map((assignmentId) => {
          const title =
            shootings.find((item) => item.assignment.assignment_id === assignmentId)
              ?.assignment.title ?? assignmentId
          const count = shootings.filter(
            (item) => item.assignment.assignment_id === assignmentId,
          ).length
          return (
            <li key={assignmentId}>
              <span
                className="route-legend-dot"
                style={{ background: colorOf(assignmentId) }}
              />
              {title} · {count}
            </li>
          )
        })}
      </ul>
    </section>
  )
}
