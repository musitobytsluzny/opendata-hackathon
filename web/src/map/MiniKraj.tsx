import { memo, type ReactNode } from 'react'
import type { Feature, Geometry, Position } from 'geojson'
import { KRAJ_BOUNDS, okresy, type OkresId } from './geo'
import { PALETTES, type PaletteId } from './palette'
import { useSettings } from '../settings/settings'
import './MiniKraj.css'

const [[W, S], [E, N]] = KRAJ_BOUNDS
const K = Math.cos((((S + N) / 2) * Math.PI) / 180)
const VB_W = Math.round((E - W) * K * 1000)
const VB_H = Math.round((N - S) * 1000)

function ring(r: Position[]): string {
  const step = Math.max(1, Math.floor(r.length / 90))
  let d = ''
  for (let i = 0; i < r.length; i += step) {
    const [lon, lat] = r[i]
    d += `${i === 0 ? 'M' : 'L'}${Math.round((lon - W) * K * 1000)},${Math.round((N - lat) * 1000)}`
  }
  return d + 'Z'
}

const SHAPES = okresy.features.map((f) => ({
  id: f.properties.id as OkresId,
  d:
    f.geometry.type === 'Polygon'
      ? f.geometry.coordinates.map(ring).join('')
      : f.geometry.coordinates.map((p) => p.map(ring).join('')).join(''),
}))

function ramp(v: number, palette: PaletteId): string {
  const STOPS: [number, number[]][] = PALETTES[palette].map((color, index) => [
    index / 2,
    [1, 3, 5].map((offset) => parseInt(color.slice(offset, offset + 2), 16)),
  ])
  const t = Math.min(1, Math.max(0, v))
  const i = t <= 0.5 ? 0 : 1
  const [a, ca] = STOPS[i]
  const [b, cb] = STOPS[i + 1]
  const k = (t - a) / (b - a)
  const c = ca.map((x, j) => Math.round(x + (cb[j] - x) * k))
  return `rgb(${c[0]} ${c[1]} ${c[2]})`
}

function drawGeometry(geometry: Geometry, key: string): ReactNode {
  const project = ([lon, lat]: Position) =>
    `${Math.round((lon - W) * K * 1000)},${Math.round((N - lat) * 1000)}`
  const line = (coordinates: Position[]) =>
    coordinates.map((point, i) => `${i ? 'L' : 'M'}${project(point)}`).join('')
  const style = { stroke: 'var(--blue-2)', strokeWidth: 8, fill: 'none' }
  switch (geometry.type) {
    case 'Point': {
      const [cx, cy] = project(geometry.coordinates).split(',')
      return <circle key={key} cx={cx} cy={cy} r={19} fill="var(--blue-2)" />
    }
    case 'LineString':
      return <path key={key} d={line(geometry.coordinates)} style={style} />
    case 'MultiLineString':
      return <path key={key} d={geometry.coordinates.map(line).join('')} style={style} />
    case 'Polygon':
      return (
        <path
          key={key}
          d={geometry.coordinates.map(ring).join('')}
          style={{ ...style, fill: 'var(--blue-2)', fillOpacity: 0.35 }}
          fillRule="evenodd"
        />
      )
    case 'MultiPolygon':
      return (
        <path
          key={key}
          d={geometry.coordinates.map((polygon) => polygon.map(ring).join('')).join('')}
          style={{ ...style, fill: 'var(--blue-2)', fillOpacity: 0.35 }}
          fillRule="evenodd"
        />
      )
    case 'MultiPoint':
      return geometry.coordinates.map((coordinates, i) =>
        drawGeometry({ type: 'Point', coordinates }, `${key}-${i}`),
      )
    case 'GeometryCollection':
      return geometry.geometries.map((part, i) => drawGeometry(part, `${key}-${i}`))
  }
}

type Props = {
  features?: Feature[]
  values?: Partial<Record<OkresId, number>> | null
  size?: number
  tone?: 'light' | 'dark'
  title?: string
}

export const MiniKraj = memo(function MiniKraj({
  values,
  features,
  size = 56,
  tone = 'light',
  title,
}: Props) {
  const { palette } = useSettings()
  const empty = tone === 'dark' ? 'rgba(255,255,255,0.14)' : '#ececea'
  return (
    <svg
      className={`mini-kraj mini-kraj--${tone}`}
      width={(size * VB_W) / VB_H}
      height={size}
      viewBox={`0 0 ${VB_W} ${VB_H}`}
      role={title ? 'img' : undefined}
      aria-label={title}
      aria-hidden={title ? undefined : true}
    >
      {SHAPES.map((s) => {
        const v = values?.[s.id]
        return <path key={s.id} d={s.d} fill={v === undefined ? empty : ramp(v, palette)} />
      })}
      {features?.map((feature, index) =>
        feature.geometry ? drawGeometry(feature.geometry, String(feature.id ?? index)) : null,
      )}
    </svg>
  )
})
