import { useMemo } from 'react'
import {
  Bar,
  BarChart,
  Brush,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { BrandSummary, RunTimeline } from '../types'

const BRAND_COLORS: Record<string, string> = {
  mts: '#ff4d4d',
  miranda: '#38d77a',
  plus7: '#38bdf8',
  other: '#facc15',
}

interface RunChartsProps {
  brands: BrandSummary[]
  timeline: RunTimeline
  onSeek: (seconds: number) => void
}

export function RunCharts({ brands, timeline, onSeek }: RunChartsProps) {
  const timelineRows = useMemo(() => {
    const rows = new Map<number, Record<string, number>>()
    timeline.points.forEach((point) => {
      const row: Record<string, number> =
        rows.get(point.bucket_start_sec) ?? {
          time: point.bucket_start_sec,
        }
      row[point.business_brand || 'other'] =
        (row[point.business_brand || 'other'] ?? 0) + point.visibility_score
      rows.set(point.bucket_start_sec, row)
    })
    return [...rows.values()].sort(
      (first, second) => Number(first.time) - Number(second.time),
    )
  }, [timeline])

  const pieData = brands.map((brand) => ({
    name: brand.brand,
    value: Number(brand.video_visibility_weighted_seconds ?? 0),
  }))

  return (
    <div className="charts-grid">
      <section className="panel chart-card">
        <header>
          <h3>Объекты по брендам</h3>
          <p>Количество уникальных рекламных объектов</p>
        </header>
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={brands}>
            <CartesianGrid stroke="rgba(255,255,255,.08)" vertical={false} />
            <XAxis dataKey="brand" stroke="#83909c" />
            <YAxis allowDecimals={false} stroke="#83909c" />
            <Tooltip />
            <Bar dataKey="object_count" radius={[6, 6, 0, 0]}>
              {brands.map((entry) => (
                <Cell
                  key={entry.brand}
                  fill={BRAND_COLORS[entry.brand] ?? BRAND_COLORS.other}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </section>

      <section className="panel chart-card">
        <header>
          <h3>Доля видимости</h3>
          <p>Взвешенное время присутствия брендов</p>
        </header>
        <ResponsiveContainer width="100%" height={300}>
          <PieChart>
            <Pie
              data={pieData}
              dataKey="value"
              nameKey="name"
              innerRadius="55%"
              outerRadius="82%"
              paddingAngle={2}
            >
              {pieData.map((entry) => (
                <Cell
                  key={entry.name}
                  fill={BRAND_COLORS[entry.name] ?? BRAND_COLORS.other}
                />
              ))}
            </Pie>
            <Tooltip />
            <Legend />
          </PieChart>
        </ResponsiveContainer>
      </section>

      <section className="panel chart-card timeline-chart">
        <header>
          <h3>Timeline видимости</h3>
          <p>Нажмите на столбец, чтобы перейти к моменту видео</p>
        </header>
        <ResponsiveContainer width="100%" height={340}>
          <BarChart
            data={timelineRows}
            onClick={(state) => {
              if (
                state &&
                typeof state === 'object' &&
                'activeLabel' in state
              ) {
                const value = state.activeLabel
                if (value !== undefined) onSeek(Number(value))
              }
            }}
          >
            <CartesianGrid stroke="rgba(255,255,255,.08)" vertical={false} />
            <XAxis
              dataKey="time"
              stroke="#83909c"
              tickFormatter={(value) => `${value}s`}
            />
            <YAxis stroke="#83909c" />
            <Tooltip labelFormatter={(value) => `${value} сек.`} />
            <Legend />
            {Object.keys(BRAND_COLORS).map((brand) => (
              <Bar
                key={brand}
                dataKey={brand}
                stackId="visibility"
                fill={BRAND_COLORS[brand]}
              />
            ))}
            <Brush dataKey="time" height={24} stroke="#ffe600" />
          </BarChart>
        </ResponsiveContainer>
      </section>
    </div>
  )
}
