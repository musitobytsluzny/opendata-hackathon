import type { FeatureCollection, Polygon, MultiPolygon, Position } from 'geojson'
import krajData from '../assets/geo/plzensky-kraj.json'
import okresyData from '../assets/geo/plzensky-kraj-okresy.json'

type Props = { name: string; id: string; kind: string }

export const kraj = krajData as unknown as FeatureCollection<Polygon | MultiPolygon, Props>
export const okresy = okresyData as unknown as FeatureCollection<Polygon | MultiPolygon, Props>

export const KRAJ_BOUNDS: [[number, number], [number, number]] = [
  [12.4005, 48.9413],
  [13.8403, 50.1044],
]

export type OkresId =
  | 'CZ0321000000'
  | 'CZ0322000000'
  | 'CZ0323000000'
  | 'CZ0324000000'
  | 'CZ0325000000'
  | 'CZ0326000000'
  | 'CZ0327000000'

export const OKRESY: Record<OkresId, { name: string; center: [number, number] }> = {
  CZ0321000000: { name: 'Domažlice', center: [12.8966, 49.4802] },
  CZ0322000000: { name: 'Klatovy', center: [13.4106, 49.2729] },
  CZ0323000000: { name: 'Plzeň-město', center: [13.42, 49.715] },
  CZ0324000000: { name: 'Plzeň-jih', center: [13.4296, 49.5667] },
  CZ0325000000: { name: 'Plzeň-sever', center: [13.284, 49.8963] },
  CZ0326000000: { name: 'Rokycany', center: [13.674, 49.8001] },
  CZ0327000000: { name: 'Tachov', center: [12.7657, 49.7682] },
}

export const TOWNS: { name: string; at: [number, number]; major?: boolean; left?: boolean }[] = [
  { name: 'Plzeň', at: [13.3776, 49.7475], major: true, left: true },
  { name: 'Klatovy', at: [13.2952, 49.3955], major: true },
  { name: 'Domažlice', at: [12.9297, 49.4405], major: true },
  { name: 'Tachov', at: [12.6336, 49.7953], major: true },
  { name: 'Rokycany', at: [13.5946, 49.7427], major: true },
  { name: 'Sušice', at: [13.5202, 49.2311] },
  { name: 'Stříbro', at: [12.9958, 49.7529] },
  { name: 'Přeštice', at: [13.3335, 49.5729] },
  { name: 'Horažďovice', at: [13.701, 49.3207] },
  { name: 'Nepomuk', at: [13.5822, 49.4862] },
  { name: 'Kralovice', at: [13.4876, 49.9819] },
  { name: 'Horšovský Týn', at: [12.9441, 49.5297] },
  { name: 'Železná Ruda', at: [13.2354, 49.1374] },
  { name: 'Planá', at: [12.7438, 49.8682] },
]

export function maskGeometry(): Polygon {
  const world: Position[] = [
    [-180, -85],
    [180, -85],
    [180, 85],
    [-180, 85],
    [-180, -85],
  ]
  const holes: Position[][] = []
  for (const f of kraj.features) {
    if (f.geometry.type === 'Polygon') holes.push(f.geometry.coordinates[0])
    else for (const p of f.geometry.coordinates) holes.push(p[0])
  }
  return { type: 'Polygon', coordinates: [world, ...holes] }
}

function boundsOf(coords: Position[][][]): [[number, number], [number, number]] {
  let w = Infinity
  let so = Infinity
  let e = -Infinity
  let n = -Infinity
  for (const poly of coords)
    for (const ring of poly)
      for (const [x, y] of ring) {
        if (x < w) w = x
        if (x > e) e = x
        if (y < so) so = y
        if (y > n) n = y
      }
  return [
    [w, so],
    [e, n],
  ]
}

export const OKRES_BOUNDS = Object.fromEntries(
  okresy.features.map((f) => [
    f.properties.id,
    boundsOf(f.geometry.type === 'Polygon' ? [f.geometry.coordinates] : f.geometry.coordinates),
  ]),
) as Record<OkresId, [[number, number], [number, number]]>
