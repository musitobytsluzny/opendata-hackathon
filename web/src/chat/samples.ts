import type { Answer } from './assistant'

// Static landing previews mirror the explicit synthetic ETL seed. They are never
// used as fallback answers by the authenticated assistant.
const source = { name: 'Ukázka pro 3 obce', publisher: 'Syntetická demo data ETL', period: '2024' }
const rows = (plzen: number, klatovy: number, rokycany: number) => [
  { okres: 'CZ0323000000' as const, value: plzen },
  { okres: 'CZ0322000000' as const, value: klatovy },
  { okres: 'CZ0326000000' as const, value: rokycany },
]
export const SAMPLES: { question: string; answer: Answer }[] = [
  {
    question: 'Kolik obyvatel mají dostupné obce v jednotlivých okresech?',
    answer: {
      text: 'V demo vzorku má Plzeň 181 200 obyvatel, Klatovy 22 140 a Rokycany 14 380. Jde o dostupné obce, nikoli celé okresy.',
      metric: 'Počet obyvatel dostupných obcí',
      short: 'Obyvatelé',
      unit: '',
      rows: rows(181200, 22140, 14380),
      source,
      sample: true,
    },
  },
  {
    question: 'Jaký je podíl seniorů v dostupných obcích?',
    answer: {
      text: 'V ukázkovém vzorku mají nejvyšší podíl seniorů Klatovy: 23,1 %. Následují Rokycany a Plzeň.',
      metric: 'Podíl seniorů v dostupných obcích',
      short: 'Senioři',
      unit: '%',
      rows: rows((37150 / 181200) * 100, (5120 / 22140) * 100, (3210 / 14380) * 100),
      source,
      sample: true,
    },
  },
  {
    question: 'Kde mají dostupné obce nejvyšší podíl zeleně?',
    answer: {
      text: 'V syntetické ukázce mají nejvyšší podíl zeleně Klatovy (68,1 %), poté Rokycany (58,9 %) a Plzeň (52,4 %).',
      metric: 'Podíl zeleně dostupných obcí',
      short: 'Zeleň',
      unit: '%',
      rows: rows(52.4, 68.1, 58.9),
      source,
      sample: true,
    },
  },
  {
    question: 'Porovnej vegetační index NDVI dostupných obcí.',
    answer: {
      text: 'Ukázkový index vegetace je nejvyšší v Klatovech (0,67), následují Rokycany (0,61) a Plzeň (0,58).',
      metric: 'Průměrný vegetační index dostupných obcí',
      short: 'Vegetace',
      unit: '',
      rows: rows(0.58, 0.67, 0.61),
      source,
      sample: true,
    },
  },
]
