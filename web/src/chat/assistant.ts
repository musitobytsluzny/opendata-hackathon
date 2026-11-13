import { OKRESY, type OkresId } from '../map/geo'

export type AnswerRow = { okres: OkresId; value: number }

export type Answer = {
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
  'Kde v kraji za posledních 10 let přibylo nejvíc obyvatel?',
  'Jaká je nezaměstnanost v jednotlivých okresech?',
  'Kolik mateřských škol je v každém okrese?',
  'Kde se v kraji staví nejvíc nových bytů?',
]

const sampleAnswers: { match: RegExp; question: string; answer: Answer }[] = [
  {
    match: /byt|výstavb|stav[ií]|dokončen/i,
    question: 'Kde se v kraji staví nejvíc nových bytů?',
    answer: {
      text: 'Nejvíc nových bytů se dokončuje v okrese Plzeň-město, v přepočtu na obyvatele ale vede Plzeň-sever.',
      metric: 'Dokončené byty na 1 000 obyvatel, 2025',
      short: 'Nové byty',
      unit: '',
      rows: [
        { okres: 'CZ0325000000', value: 6.8 },
        { okres: 'CZ0323000000', value: 5.9 },
        { okres: 'CZ0324000000', value: 5.1 },
        { okres: 'CZ0326000000', value: 3.7 },
        { okres: 'CZ0321000000', value: 2.6 },
        { okres: 'CZ0322000000', value: 2.2 },
        { okres: 'CZ0327000000', value: 1.8 },
      ],
      source: { name: 'Bytová výstavba v obcích', publisher: 'Český statistický úřad', period: '2025' },
      sample: true,
    },
  },
  {
    match: /obyvatel|lidí|populac|přibyl|roste|stěhov/i,
    question: 'Kde v kraji za posledních 10 let přibylo nejvíc obyvatel?',
    answer: {
      text: 'Nejrychleji roste okres Plzeň-sever, hlavně obce v okolí Plzně. Pokles je jen na Klatovsku a Tachovsku.',
      metric: 'Změna počtu obyvatel 2014–2024',
      short: 'Obyvatelé',
      unit: '%',
      signed: true,
      rows: [
        { okres: 'CZ0325000000', value: 9.8 },
        { okres: 'CZ0324000000', value: 6.1 },
        { okres: 'CZ0326000000', value: 4.3 },
        { okres: 'CZ0323000000', value: 3.2 },
        { okres: 'CZ0321000000', value: 0.4 },
        { okres: 'CZ0327000000', value: -0.9 },
        { okres: 'CZ0322000000', value: -1.6 },
      ],
      source: { name: 'Počet obyvatel v obcích', publisher: 'Český statistický úřad', period: '2014–2024' },
      sample: true,
    },
  },
  {
    match: /nezaměstna|práce|zaměstna/i,
    question: 'Jaká je nezaměstnanost v jednotlivých okresech?',
    answer: {
      text: 'Nejvyšší podíl nezaměstnaných má okres Tachov, nejnižší Plzeň-sever. Krajský průměr je kolem 2,9 %.',
      metric: 'Podíl nezaměstnaných osob',
      short: 'Nezaměstnanost',
      unit: '%',
      rows: [
        { okres: 'CZ0327000000', value: 4.1 },
        { okres: 'CZ0321000000', value: 3.4 },
        { okres: 'CZ0322000000', value: 3.1 },
        { okres: 'CZ0323000000', value: 2.9 },
        { okres: 'CZ0326000000', value: 2.6 },
        { okres: 'CZ0324000000', value: 2.2 },
        { okres: 'CZ0325000000', value: 1.9 },
      ],
      source: { name: 'Podíl nezaměstnaných osob', publisher: 'MPSV', period: 'září 2026' },
      sample: true,
    },
  },
  {
    match: /škol|školk|vzdělá/i,
    question: 'Kolik mateřských škol je v každém okrese?',
    answer: {
      text: 'Nejvíc mateřských škol má okres Klatovy, i když nejvíc dětí bydlí v Plzni. Plzeň-město má méně, ale větších školek.',
      metric: 'Počet mateřských škol',
      short: 'Školky',
      unit: '',
      rows: [
        { okres: 'CZ0322000000', value: 58 },
        { okres: 'CZ0323000000', value: 52 },
        { okres: 'CZ0324000000', value: 47 },
        { okres: 'CZ0325000000', value: 45 },
        { okres: 'CZ0321000000', value: 39 },
        { okres: 'CZ0326000000', value: 31 },
        { okres: 'CZ0327000000', value: 27 },
      ],
      source: { name: 'Rejstřík škol a školských zařízení', publisher: 'MŠMT', period: '2025/26' },
      sample: true,
    },
  },
]

export const SAMPLES = sampleAnswers.map(({ question, answer }) => ({ question, answer }))

export async function ask(question: string): Promise<Answer> {
  await new Promise((r) => setTimeout(r, 900 + Math.random() * 500))
  if (/chyba|error/i.test(question)) throw new Error('Datový zdroj neodpověděl včas.')
  const hit = sampleAnswers.find((a) => a.match.test(question))
  if (hit) return hit.answer
  return {
    text: 'K této otázce zatím nemám v otevřených datech kraje nic spolehlivého. Zkuste se zeptat na obyvatele, nezaměstnanost nebo školy.',
    sample: true,
  }
}

export function formatValue(v: number, unit = '', signed = false): string {
  const s = new Intl.NumberFormat('cs-CZ', { maximumFractionDigits: 1 }).format(Math.abs(v))
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
