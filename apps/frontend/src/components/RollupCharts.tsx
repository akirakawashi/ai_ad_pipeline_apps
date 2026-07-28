import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ErrorBar,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { Aggregate, RollupBrand, ShootingMetrics } from '../types'
import { formatDuration, statValue } from '../utils/formatters'

const BRAND_COLORS: Record<string, string> = {
  mts: '#ff4d4d',
  miranda: '#05c3a1',
  plus7: '#58a6ff',
  other: '#b8bec6',
}

const BRAND_LABELS: Record<string, string> = {
  mts: 'МТС',
  miranda: 'Miranda',
  plus7: '+7',
  other: 'Другое',
}

const BRAND_ORDER = ['mts', 'plus7', 'miranda', 'other']

const tooltipStyle = {
  background: '#151515',
  border: '1px solid rgba(255,255,255,.14)',
  borderRadius: 8,
  color: '#f4f4f4',
}

const tooltipCursor = { fill: 'rgba(255,255,255,.06)' }

function brandColor(brand: string) {
  return BRAND_COLORS[brand] ?? '#e7c84d'
}

function brandLabel(brand: string) {
  return BRAND_LABELS[brand] ?? brand.toUpperCase()
}

function orderBrands(brands: string[]) {
  return [...brands].sort((a, b) => {
    const ai = BRAND_ORDER.indexOf(a)
    const bi = BRAND_ORDER.indexOf(b)
    return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi)
  })
}

export function RollupCharts({
  brands,
  shootings,
  aggregate,
}: {
  brands: RollupBrand[]
  shootings: ShootingMetrics[]
  aggregate: Aggregate
}) {
  // Доля считается здесь, а не на сервере: она зависит от выбранной оценки, а
  // выбор живёт на этой странице.
  const totalVisibility = brands.reduce(
    (sum, item) => sum + statValue(item.visibility_per_shooting, aggregate),
    0,
  )

  // Усы = разброс между съёмками. Это не украшение: широкий ус означает,
  // что съёмки разошлись и цифре верить рано.
  const brandRows = brands.map((item) => {
    const visibility = statValue(item.visibility_per_shooting, aggregate)
    return {
      brand_key: item.brand,
      brand_label: brandLabel(item.brand),
      objects: Number(statValue(item.objects_per_shooting, aggregate).toFixed(2)),
      objects_std: Number(item.objects_per_shooting.std.toFixed(2)),
      share: Number(
        (totalVisibility > 0 ? (visibility / totalVisibility) * 100 : 0).toFixed(1),
      ),
    }
  })

  const passBrands = orderBrands([
    ...new Set(shootings.flatMap((item) => item.brands.map((b) => b.brand))),
  ])

  const shootingRows = shootings.map((item, index) => {
    const row: Record<string, number | string> = {
      name: `№${index + 1}`,
      source_name: item.source_name,
      duration: item.duration_sec,
      duration_label: formatDuration(item.duration_sec),
    }
    passBrands.forEach((brand) => {
      row[brand] =
        item.brands.find((entry) => entry.brand === brand)?.objects_count ?? 0
    })
    return row
  })

  return (
    <div className="charts-grid">
      <section className="panel chart-card">
        <header>
          <h3>Объектов за съёмку</h3>
          <p>
            {aggregate === 'median' ? 'Медиана' : 'Среднее'} по съёмкам. Усы —
            разброс между ними.
          </p>
        </header>
        <ResponsiveContainer width="100%" height={280}>
          <BarChart data={brandRows}>
            <CartesianGrid stroke="rgba(255,255,255,.08)" vertical={false} />
            <XAxis dataKey="brand_label" stroke="#8d9298" />
            <YAxis stroke="#8d9298" />
            <Tooltip contentStyle={tooltipStyle} cursor={tooltipCursor} />
            <Bar dataKey="objects" name="За съёмку" radius={[6, 6, 0, 0]}>
              {brandRows.map((row) => (
                <Cell key={row.brand_key} fill={brandColor(row.brand_key)} />
              ))}
              <ErrorBar
                dataKey="objects_std"
                stroke="#f4f4f4"
                strokeWidth={1.5}
                width={4}
              />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </section>

      <section className="panel chart-card">
        <header>
          <h3>Доля заметности</h3>
          <p>
            Сколько внимания забирает каждый бренд за съёмку.
            {aggregate === 'median' &&
              ' Под медианой доли не сходятся в 100 %: медиана суммы не равна' +
                ' сумме медиан.'}
          </p>
        </header>
        <ResponsiveContainer width="100%" height={280}>
          <PieChart>
            <Pie
              data={brandRows}
              dataKey="share"
              nameKey="brand_label"
              innerRadius={60}
              outerRadius={100}
              paddingAngle={2}
            >
              {brandRows.map((row) => (
                <Cell key={row.brand_key} fill={brandColor(row.brand_key)} />
              ))}
            </Pie>
            <Tooltip
              contentStyle={tooltipStyle}
              formatter={(value) => `${value}%`}
            />
            <Legend />
          </PieChart>
        </ResponsiveContainer>
      </section>

      <section className="panel chart-card wide-chart">
        <header>
          <h3>Сравнение съёмок</h3>
          <p>
            Каждый столбец — одна съёмка. Выбивающаяся съёмка видна сразу;
            смотрите на его длительность в подсказке.
          </p>
        </header>
        <ResponsiveContainer width="100%" height={320}>
          <BarChart data={shootingRows}>
            <CartesianGrid stroke="rgba(255,255,255,.08)" vertical={false} />
            <XAxis dataKey="name" stroke="#8d9298" />
            <YAxis allowDecimals={false} stroke="#8d9298" />
            <Tooltip
              contentStyle={tooltipStyle}
              cursor={tooltipCursor}
              labelFormatter={(_, payload) => {
                const row = payload?.[0]?.payload
                return row
                  ? `${row.source_name} · ${row.duration_label}`
                  : ''
              }}
            />
            <Legend />
            {passBrands.map((brand) => (
              <Bar
                key={brand}
                dataKey={brand}
                name={brandLabel(brand)}
                stackId="shootings"
                fill={brandColor(brand)}
              />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </section>
    </div>
  )
}
