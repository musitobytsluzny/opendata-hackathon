import type { Position } from 'geojson'
import { KRAJ_BOUNDS, okresy, type OkresId } from './geo'
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

const STOPS: [number, [number, number, number]][] = [
  [0, [220, 232, 246]],
  [0.5, [91, 147, 211]],
  [1, [27, 76, 133]],
]

export function ramp(v: number): string {
  const t = Math.min(1, Math.max(0, v))
  const i = t <= 0.5 ? 0 : 1
  const [a, ca] = STOPS[i]
  const [b, cb] = STOPS[i + 1]
  const k = (t - a) / (b - a)
  const c = ca.map((x, j) => Math.round(x + (cb[j] - x) * k))
  return `rgb(${c[0]} ${c[1]} ${c[2]})`
}

type Props = {
  values?: Partial<Record<OkresId, number>> | null
  size?: number
  tone?: 'light' | 'dark'
  title?: string
}

export function MiniKraj({ values, size = 56, tone = 'light', title }: Props) {
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
        return <path key={s.id} d={s.d} fill={v === undefined ? empty : ramp(v)} />
      })}
    </svg>
  )
}
