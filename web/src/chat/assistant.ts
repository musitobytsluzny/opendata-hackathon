import type { Feature } from 'geojson'
import { apiFetch } from '../api/client'
import { OKRESY, type OkresId } from '../map/geo'

export type AnswerRow = { okres: OkresId; value: number }

export type Artifact = {
  result_id: string
  title: string
  view: 'table' | 'map' | 'bar' | 'line' | 'pie'
  columns: { key: string; label: string; numeric: boolean; additive?: boolean; unit: string }[]
  rows: Record<string, string | number | boolean | null>[]
  features: Feature[]
  sources: { table_name?: string; name?: string; data_kind?: string; loaded_at?: string }[]
  note: string
  sample: boolean
  value_key?: string | null
  label_key?: string | null
}

export type Answer = {
  artifacts?: Artifact[]
  layer_actions?: { result_id: string; visible: boolean }[]
  text: string
  metric?: string
  short?: string
  unit?: string
  signed?: boolean
  rows?: AnswerRow[]
  source?: { name: string; publisher: string; period: string }
  sample: boolean
}

export type Message =
  | { id: string; role: 'user'; text: string }
  | { id: string; role: 'assistant'; answer: Answer }
  | { id: string; role: 'error'; text: string; retry: string }

export const PENDING_QUESTION_KEY = 'pending_question'

export const SUGGESTIONS = [
  'Kolik obyvatel mají dostupné obce v jednotlivých okresech?',
  'Jaký je podíl seniorů v dostupných obcích?',
  'Kde mají dostupné obce nejvyšší podíl zeleně?',
  'Porovnej 10 největších obcí podle počtu obyvatel v grafu a na mapě.',
  'Najdi silniční trasu mezi Plzní a Klatovy a ukaž ji na mapě.',
]

export async function ask(
  question: string,
  history: Message[] = [],
  signal?: AbortSignal,
): Promise<Answer> {
  const resultIds = [
    ...new Set(
      history.flatMap((message) =>
        message.role === 'assistant'
          ? (message.answer.artifacts ?? []).map((item) => item.result_id)
          : [],
      ),
    ),
  ].slice(-8)
  return apiFetch<Answer>('/chat/ask', {
    method: 'POST',
    body: JSON.stringify({
      question,
      ...(resultIds.length ? { result_ids: resultIds } : {}),
      history: history
        .filter((message) => message.role !== 'error')
        .slice(-10)
        .map((message) => ({
          role: message.role,
          text: (message.role === 'assistant' ? message.answer.text : message.text).slice(0, 2000),
        })),
    }),
    signal,
  })
}

const valueFormat = new Intl.NumberFormat('cs-CZ', { maximumFractionDigits: 2 })

export function formatValue(v: number, unit = '', signed = false): string {
  const s = valueFormat.format(Math.abs(v))
  const sign = v < 0 ? '−' : signed && v > 0 ? '+' : ''
  return unit ? `${sign}${s} ${unit}` : `${sign}${s}`
}

export function normalize(rows: AnswerRow[]): Partial<Record<OkresId, number>> {
  const vals = rows.map((r) => r.value)
  const min = Math.min(...vals)
  const max = Math.max(...vals)
  const span = max - min || 1
  return Object.fromEntries(rows.map((r) => [r.okres, (r.value - min) / span]))
}

export function okresName(id: OkresId): string {
  return OKRESY[id].name
}
