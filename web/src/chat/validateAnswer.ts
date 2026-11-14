import type { Feature, Geometry } from 'geojson'
import type { Answer, Artifact } from './assistant'

const record = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === 'object' && !Array.isArray(value)
const finite = (value: unknown): value is number =>
  typeof value === 'number' && Number.isFinite(value)
const scalar = (value: unknown) =>
  value === null || typeof value === 'string' || typeof value === 'boolean' || finite(value)
const views = new Set(['map', 'table', 'bar', 'line', 'pie'])
function coordinates(value: unknown, depth = 0): boolean {
  if (!Array.isArray(value) || !value.length || depth > 4) return false
  return typeof value[0] === 'number'
    ? value.length >= 2 &&
        value.every(finite) &&
        Math.abs(value[0]) <= 180 &&
        Math.abs(value[1]) <= 90
    : value.every((item) => coordinates(item, depth + 1))
}
function geometry(value: unknown, depth = 0): value is Geometry {
  if (!record(value) || depth > 8) return false
  if (value.type === 'GeometryCollection')
    return (
      Array.isArray(value.geometries) && value.geometries.every((item) => geometry(item, depth + 1))
    )
  return (
    ['Point', 'MultiPoint', 'LineString', 'MultiLineString', 'Polygon', 'MultiPolygon'].includes(
      String(value.type),
    ) && coordinates(value.coordinates)
  )
}
function feature(value: unknown): value is Feature {
  return (
    record(value) &&
    value.type === 'Feature' &&
    geometry(value.geometry) &&
    (value.properties == null || record(value.properties))
  )
}
function artifact(value: unknown): Artifact | null {
  if (
    !record(value) ||
    typeof value.result_id !== 'string' ||
    value.result_id.length > 60 ||
    typeof value.title !== 'string' ||
    !views.has(String(value.view))
  )
    return null
  if (
    !Array.isArray(value.columns) ||
    value.columns.length > 12 ||
    !value.columns.every(
      (col) => record(col) && typeof col.key === 'string' && typeof col.label === 'string',
    )
  )
    return null
  if (
    !Array.isArray(value.rows) ||
    value.rows.length > 50 ||
    !value.rows.every((row) => record(row) && Object.values(row).every(scalar))
  )
    return null
  if (
    !Array.isArray(value.features) ||
    value.features.length > 256 ||
    !value.features.every(feature)
  )
    return null
  return {
    ...value,
    sample: value.sample === true,
    note: typeof value.note === 'string' ? value.note : '',
    sources: Array.isArray(value.sources) ? value.sources.filter(record) : [],
    columns: value.columns.map((col) => ({
      ...col,
      numeric: col.numeric === true,
      unit: typeof col.unit === 'string' ? col.unit : '',
    })),
  } as Artifact
}

// Server JSON and persisted history are both untrusted at the rendering boundary.
export function validateAnswer(value: unknown): Answer | null {
  if (!record(value) || typeof value.text !== 'string') return null
  const answer: Answer = { text: value.text, sample: value.sample === true }
  if (Array.isArray(value.artifacts))
    answer.artifacts = value.artifacts
      .slice(0, 12)
      .map(artifact)
      .filter((item): item is Artifact => item !== null)
  if (Array.isArray(value.result_ids))
    answer.result_ids = value.result_ids
      .filter((id): id is string => typeof id === 'string' && id.length <= 60)
      .slice(-8)
  if (Array.isArray(value.layer_actions))
    answer.layer_actions = value.layer_actions
      .filter(
        (action) =>
          record(action) &&
          typeof action.result_id === 'string' &&
          typeof action.visible === 'boolean',
      )
      .slice(0, 12) as NonNullable<Answer['layer_actions']>
  if (Array.isArray(value.rows))
    answer.rows = value.rows.filter(
      (row) => record(row) && /^CZ032[1-7]000000$/.test(String(row.okres)) && finite(row.value),
    ) as NonNullable<Answer['rows']>
  for (const key of ['metric', 'short', 'unit'] as const)
    if (typeof value[key] === 'string') answer[key] = value[key]
  if (typeof value.signed === 'boolean') answer.signed = value.signed
  if (
    record(value.source) &&
    ['name', 'publisher', 'period'].every(
      (key) => typeof (value.source as Record<string, unknown>)[key] === 'string',
    )
  )
    answer.source = value.source as Answer['source']
  return answer
}
