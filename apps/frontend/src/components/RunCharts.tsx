import { useMemo, useState, type CSSProperties } from 'react'
import {
  Bar,
  BarChart,
  Brush,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { BrandSummary, RunObject, RunTimeline } from '../types'

const BRAND_COLORS: Record<string, string> = {
  mts: '#ff4d4d',
  miranda: '#05c3a1',
  plus7: '#58a6ff',
  other: '#b8bec6',
}

const BRAND_ORDER = ['mts', 'miranda', 'plus7', 'other']
const FALLBACK_COLORS = ['#e7c84d', '#a78bfa', '#fb923c', '#22d3ee']

const tooltipStyle = {
  background: '#151515',
  border: '1px solid rgba(255,255,255,.14)',
  borderRadius: 8,
  color: '#f4f4f4',
}

interface RunChartsProps {
  brands: BrandSummary[]
  objects: RunObject[]
  timeline: RunTimeline
  onSeek: (seconds: number) => void
}

interface BrandChartRow {
  brand_key: string
  brand_label: string
  object_count: number
  visibility_index: number
  mean_confidence_percent: number
}

type ChartRow = Record<string, number>

export function RunCharts({
  brands,
  objects,
  timeline,
  onSeek,
}: RunChartsProps) {
  const [hiddenBrands, setHiddenBrands] = useState<Set<string>>(new Set())

  const availableBrands = useMemo(() => {
    const values = new Set<string>()
    brands.forEach((brand) => values.add(normalizeBrand(brand.brand)))
    objects.forEach((object) =>
      values.add(normalizeBrand(object.business_brand)),
    )
    timeline.points.forEach((point) =>
      values.add(normalizeBrand(point.business_brand)),
    )
    return [...values].sort(compareBrands)
  }, [brands, objects, timeline])

  const visibleBrandKeys = useMemo(
    () => availableBrands.filter((brand) => !hiddenBrands.has(brand)),
    [availableBrands, hiddenBrands],
  )

  const brandRows = useMemo(
    () =>
      brands
        .map(toBrandChartRow)
        .filter((brand) => !hiddenBrands.has(brand.brand_key)),
    [brands, hiddenBrands],
  )

  const visibilityTimelineRows = useMemo(
    () =>
      buildTimelineRows(
        timeline,
        hiddenBrands,
        (point) => point.visibility_score,
      ),
    [hiddenBrands, timeline],
  )

  const detectionTimelineRows = useMemo(
    () =>
      buildTimelineRows(
        timeline,
        hiddenBrands,
        (point) => point.detection_count,
      ),
    [hiddenBrands, timeline],
  )

  const pieData = brandRows.map((brand) => ({
    name: brand.brand_label,
    brand_key: brand.brand_key,
    value: brand.visibility_index,
  }))

  const topObjectRows = useMemo(
    () =>
      objects
        .map((object) => ({
          ...object,
          brand_key: normalizeBrand(object.business_brand),
          brand_label: formatBrandLabel(object.business_brand),
          label: `${formatBrandLabel(object.business_brand)} · ${formatDurationLabel(
            object.best_timestamp_sec,
          )}`,
          visibility_index: Number(
            object.video_visibility_weighted_seconds ?? 0,
          ),
        }))
        .filter((object) => !hiddenBrands.has(object.brand_key))
        .sort((first, second) => second.visibility_index - first.visibility_index)
        .slice(0, 10),
    [hiddenBrands, objects],
  )

  const toggleBrand = (brand: string) => {
    setHiddenBrands((current) => {
      const next = new Set(current)
      if (next.has(brand)) {
        next.delete(brand)
      } else {
        next.add(brand)
      }
      return next
    })
  }

  return (
    <>
      <section className="charts-toolbar" aria-label="Фильтр брендов">
        <span>Бренды на графиках</span>
        <div className="brand-filter">
          {availableBrands.map((brand) => {
            const hidden = hiddenBrands.has(brand)
            return (
              <button
                className={`brand-toggle${hidden ? ' hidden' : ''}`}
                key={brand}
                onClick={() => toggleBrand(brand)}
                style={
                  { '--brand-color': getBrandColor(brand) } as CSSProperties
                }
                type="button"
                aria-pressed={!hidden}
              >
                <span />
                {formatBrandLabel(brand)}
              </button>
            )
          })}
        </div>
      </section>

      <div className="charts-grid">
        <section className="panel chart-card">
          <header>
            <h3>Объекты по брендам</h3>
            <p>Количество уникальных рекламных объектов</p>
          </header>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={brandRows}>
              <CartesianGrid stroke="rgba(255,255,255,.08)" vertical={false} />
              <XAxis dataKey="brand_label" stroke="#8d9298" />
              <YAxis allowDecimals={false} stroke="#8d9298" />
              <Tooltip contentStyle={tooltipStyle} />
              <Bar dataKey="object_count" name="Объекты" radius={[6, 6, 0, 0]}>
                {brandRows.map((entry) => (
                  <Cell
                    key={entry.brand_key}
                    fill={getBrandColor(entry.brand_key)}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </section>

        <section className="panel chart-card">
          <header>
            <h3>Индекс заметности</h3>
            <p>Взвешенное время присутствия брендов</p>
          </header>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={brandRows}>
              <CartesianGrid stroke="rgba(255,255,255,.08)" vertical={false} />
              <XAxis dataKey="brand_label" stroke="#8d9298" />
              <YAxis stroke="#8d9298" />
              <Tooltip contentStyle={tooltipStyle} />
              <Bar
                dataKey="visibility_index"
                name="Visibility index"
                radius={[6, 6, 0, 0]}
              >
                {brandRows.map((entry) => (
                  <Cell
                    key={entry.brand_key}
                    fill={getBrandColor(entry.brand_key)}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </section>

        <section className="panel chart-card">
          <header>
            <h3>Доля видимости</h3>
            <p>Процентная доля visibility index</p>
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
                    key={entry.brand_key}
                    fill={getBrandColor(entry.brand_key)}
                  />
                ))}
              </Pie>
              <Tooltip contentStyle={tooltipStyle} />
            </PieChart>
          </ResponsiveContainer>
        </section>

        <section className="panel chart-card">
          <header>
            <h3>Объекты vs заметность</h3>
            <p>Количество объектов и visibility index на одной шкале брендов</p>
          </header>
          <ResponsiveContainer width="100%" height={300}>
            <ComposedChart data={brandRows}>
              <CartesianGrid stroke="rgba(255,255,255,.08)" vertical={false} />
              <XAxis dataKey="brand_label" stroke="#8d9298" />
              <YAxis
                yAxisId="count"
                allowDecimals={false}
                stroke="#8d9298"
              />
              <YAxis
                yAxisId="visibility"
                orientation="right"
                stroke="#05c3a1"
              />
              <Tooltip contentStyle={tooltipStyle} />
              <Legend />
              <Bar
                yAxisId="count"
                dataKey="object_count"
                name="Объекты"
                fill="#94a3b8"
                radius={[6, 6, 0, 0]}
              />
              <Line
                yAxisId="visibility"
                type="monotone"
                dataKey="visibility_index"
                name="Visibility index"
                stroke="#05c3a1"
                strokeWidth={3}
                dot={{ r: 5 }}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </section>

        <section className="panel chart-card">
          <header>
            <h3>Уверенность классификации</h3>
            <p>Средняя confidence итогового бренда</p>
          </header>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={brandRows}>
              <CartesianGrid stroke="rgba(255,255,255,.08)" vertical={false} />
              <XAxis dataKey="brand_label" stroke="#8d9298" />
              <YAxis
                stroke="#8d9298"
                domain={[0, 100]}
                tickFormatter={(value) => `${value}%`}
              />
              <Tooltip contentStyle={tooltipStyle} />
              <Bar
                dataKey="mean_confidence_percent"
                name="Brand confidence, %"
                radius={[6, 6, 0, 0]}
              >
                {brandRows.map((entry) => (
                  <Cell
                    key={entry.brand_key}
                    fill={getBrandColor(entry.brand_key)}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </section>

        <section className="panel chart-card wide-chart">
          <header>
            <h3>Топ заметных объектов</h3>
            <p>Клик по строке перематывает видео на лучший момент объекта</p>
          </header>
          <ResponsiveContainer width="100%" height={360}>
            <BarChart
              data={topObjectRows}
              layout="vertical"
              margin={{ left: 20, right: 32 }}
              onClick={(state) => {
                const seconds = activePayloadNumber(state, 'best_timestamp_sec')
                if (seconds !== null) onSeek(seconds)
              }}
            >
              <CartesianGrid stroke="rgba(255,255,255,.08)" horizontal={false} />
              <XAxis type="number" stroke="#8d9298" />
              <YAxis
                dataKey="label"
                type="category"
                width={130}
                stroke="#8d9298"
              />
              <Tooltip contentStyle={tooltipStyle} />
              <Bar
                dataKey="visibility_index"
                name="Visibility index"
                radius={[0, 8, 8, 0]}
              >
                {topObjectRows.map((entry) => (
                  <Cell
                    key={`${entry.track_id}-${entry.best_timestamp_sec}`}
                    fill={getBrandColor(entry.brand_key)}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </section>

        <section className="panel chart-card wide-chart">
          <header>
            <h3>Timeline видимости</h3>
            <p>Нажмите на столбец, чтобы перейти к моменту видео</p>
          </header>
          <ResponsiveContainer width="100%" height={340}>
            <BarChart
              data={visibilityTimelineRows}
              onClick={(state) => {
                const seconds = activeLabelNumber(state)
                if (seconds !== null) onSeek(seconds)
              }}
            >
              <CartesianGrid stroke="rgba(255,255,255,.08)" vertical={false} />
              <XAxis
                dataKey="time"
                stroke="#8d9298"
                tickFormatter={(value) => `${value}s`}
              />
              <YAxis stroke="#8d9298" />
              <Tooltip
                contentStyle={tooltipStyle}
                labelFormatter={(value) => `${value} сек.`}
              />
              {visibleBrandKeys.map((brand) => (
                <Bar
                  key={brand}
                  dataKey={brand}
                  stackId="visibility"
                  fill={getBrandColor(brand)}
                />
              ))}
              <Brush dataKey="time" height={24} stroke="#05c3a1" />
            </BarChart>
          </ResponsiveContainer>
        </section>

        <section className="panel chart-card wide-chart">
          <header>
            <h3>Детекции по времени</h3>
            <p>Количество видимых детекций по временным окнам</p>
          </header>
          <ResponsiveContainer width="100%" height={320}>
            <BarChart
              data={detectionTimelineRows}
              onClick={(state) => {
                const seconds = activeLabelNumber(state)
                if (seconds !== null) onSeek(seconds)
              }}
            >
              <CartesianGrid stroke="rgba(255,255,255,.08)" vertical={false} />
              <XAxis
                dataKey="time"
                stroke="#8d9298"
                tickFormatter={(value) => `${value}s`}
              />
              <YAxis allowDecimals={false} stroke="#8d9298" />
              <Tooltip
                contentStyle={tooltipStyle}
                labelFormatter={(value) => `${value} сек.`}
              />
              {visibleBrandKeys.map((brand) => (
                <Bar
                  key={brand}
                  dataKey={brand}
                  stackId="detections"
                  fill={getBrandColor(brand)}
                />
              ))}
              <Brush dataKey="time" height={24} stroke="#05c3a1" />
            </BarChart>
          </ResponsiveContainer>
        </section>
      </div>
    </>
  )
}

function toBrandChartRow(brand: BrandSummary): BrandChartRow {
  const brandKey = normalizeBrand(brand.brand)
  return {
    brand_key: brandKey,
    brand_label: formatBrandLabel(brandKey),
    object_count: Number(brand.object_count ?? 0),
    visibility_index: Number(brand.video_visibility_weighted_seconds ?? 0),
    mean_confidence_percent: Number(brand.mean_final_brand_conf ?? 0) * 100,
  }
}

function buildTimelineRows(
  timeline: RunTimeline,
  hiddenBrands: Set<string>,
  valueSelector: (point: RunTimeline['points'][number]) => number,
): ChartRow[] {
  const rows = new Map<number, ChartRow>()
  timeline.points.forEach((point) => {
    const brand = normalizeBrand(point.business_brand)
    if (hiddenBrands.has(brand)) return

    const row = rows.get(point.bucket_start_sec) ?? {
      time: point.bucket_start_sec,
    }
    row[brand] = (row[brand] ?? 0) + Number(valueSelector(point) ?? 0)
    rows.set(point.bucket_start_sec, row)
  })
  return [...rows.values()].sort(
    (first, second) => Number(first.time) - Number(second.time),
  )
}

function activeLabelNumber(state: unknown): number | null {
  if (!state || typeof state !== 'object' || !('activeLabel' in state)) {
    return null
  }
  const value = state.activeLabel
  const numeric = Number(value)
  return Number.isFinite(numeric) ? numeric : null
}

function activePayloadNumber(state: unknown, key: string): number | null {
  if (!state || typeof state !== 'object' || !('activePayload' in state)) {
    return null
  }
  const payload = state.activePayload
  if (!Array.isArray(payload)) return null

  const value = (payload[0] as { payload?: Record<string, unknown> } | undefined)
    ?.payload?.[key]
  const numeric = Number(value)
  return Number.isFinite(numeric) ? numeric : null
}

function normalizeBrand(value: string | null | undefined): string {
  return (value || 'other').toLowerCase()
}

function compareBrands(first: string, second: string): number {
  const firstIndex = BRAND_ORDER.indexOf(first)
  const secondIndex = BRAND_ORDER.indexOf(second)
  const firstOrder = firstIndex === -1 ? BRAND_ORDER.length : firstIndex
  const secondOrder = secondIndex === -1 ? BRAND_ORDER.length : secondIndex
  if (firstOrder !== secondOrder) return firstOrder - secondOrder
  return first.localeCompare(second)
}

function formatBrandLabel(brand: string): string {
  return brand.toUpperCase()
}

function formatDurationLabel(seconds: number): string {
  return `${seconds.toFixed(1)}s`
}

function getBrandColor(brand: string): string {
  if (BRAND_COLORS[brand]) return BRAND_COLORS[brand]
  const hash = [...brand].reduce(
    (result, character) => result + character.charCodeAt(0),
    0,
  )
  return FALLBACK_COLORS[hash % FALLBACK_COLORS.length]
}
