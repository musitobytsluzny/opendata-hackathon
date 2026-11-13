import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { Icon } from '../components/Icon'
import {
  PENDING_QUESTION_KEY,
  SAMPLES,
  formatValue,
  normalize,
  type Answer,
} from '../chat/assistant'
import { MiniKraj } from '../map/MiniKraj'
import { RegionMap } from '../map/LazyRegionMap'
import { navigate, routes } from '../router/router'
import { Link } from '../router/Link'
import { useAuth } from '../auth/AuthContext'
import './LandingPage.css'

const DEMOS: { q: string; a: Answer }[] = [
  {
    q: 'Kde v kraji přibylo nejvíc obyvatel?',
    a: {
      text: 'Nejrychleji roste Plzeň-sever, hlavně obce kolem Plzně.',
      unit: '%',
      signed: true,
      metric: 'Změna počtu obyvatel 2014–2024',
      rows: [
        { okres: 'CZ0325000000', value: 9.8 },
        { okres: 'CZ0324000000', value: 6.1 },
        { okres: 'CZ0326000000', value: 4.3 },
        { okres: 'CZ0323000000', value: 3.2 },
        { okres: 'CZ0321000000', value: 0.4 },
        { okres: 'CZ0327000000', value: -0.9 },
        { okres: 'CZ0322000000', value: -1.6 },
      ],
      sample: true,
    },
  },
  {
    q: 'Kde je nejvyšší nezaměstnanost?',
    a: {
      text: 'Nejvíc lidí bez práce hledá na Tachovsku, nejméně v okrese Plzeň-sever.',
      unit: '%',
      metric: 'Podíl nezaměstnaných osob',
      rows: [
        { okres: 'CZ0327000000', value: 4.1 },
        { okres: 'CZ0321000000', value: 3.4 },
        { okres: 'CZ0322000000', value: 3.1 },
        { okres: 'CZ0323000000', value: 2.9 },
        { okres: 'CZ0326000000', value: 2.6 },
        { okres: 'CZ0324000000', value: 2.2 },
        { okres: 'CZ0325000000', value: 1.9 },
      ],
      sample: true,
    },
  },
]

const SAMPLE_CARDS = SAMPLES.map((sample) => ({
  ...sample,
  values: sample.answer.rows ? normalize(sample.answer.rows) : null,
}))

type Phase = 'typing' | 'thinking' | 'answer'

function useDemo() {
  const reduced = useMemo(() => window.matchMedia('(prefers-reduced-motion: reduce)').matches, [])
  const [index, setIndex] = useState(0)
  const [typed, setTyped] = useState(reduced ? DEMOS[0].q.length : 0)
  const [phase, setPhase] = useState<Phase>(reduced ? 'answer' : 'typing')

  useEffect(() => {
    if (reduced) return
    const q = DEMOS[index].q
    let t: number
    if (phase === 'typing') {
      t = window.setTimeout(
        () => (typed < q.length ? setTyped(typed + 1) : setPhase('thinking')),
        typed === 0 ? 700 : 38,
      )
    } else if (phase === 'thinking') {
      t = window.setTimeout(() => setPhase('answer'), 900)
    } else {
      t = window.setTimeout(() => {
        setIndex((index + 1) % DEMOS.length)
        setTyped(0)
        setPhase('typing')
      }, 6500)
    }
    return () => window.clearTimeout(t)
  }, [index, typed, phase, reduced])

  return { demo: DEMOS[index], index, typed, phase }
}

export function LandingPage() {
  const { user } = useAuth()
  const { demo, typed, phase } = useDemo()
  const [question, setQuestion] = useState('')

  const shown = phase === 'answer' ? demo.a : null
  const values = useMemo(() => (shown?.rows ? normalize(shown.rows) : null), [shown])
  const labels = useMemo(
    () =>
      shown?.rows
        ? Object.fromEntries(
            shown.rows.map((r) => [r.okres, formatValue(r.value, shown.unit, shown.signed)]),
          )
        : null,
    [shown],
  )

  const [narrow, setNarrow] = useState(() => window.matchMedia('(max-width: 900px)').matches)
  useEffect(() => {
    const mq = window.matchMedia('(max-width: 900px)')
    const on = () => setNarrow(mq.matches)
    mq.addEventListener('change', on)
    return () => mq.removeEventListener('change', on)
  }, [])
  const heroPadding = useMemo(
    () =>
      narrow
        ? { top: 100, right: 56, bottom: 400, left: 56 }
        : { top: 120, right: 72, bottom: 72, left: Math.round(window.innerWidth * 0.46) },
    [narrow],
  )

  const start = user ? routes.map : `${routes.login}?registrace`

  function askAndStart(q: string) {
    try {
      sessionStorage.setItem(PENDING_QUESTION_KEY, q)
    } catch {}
    navigate(start)
  }

  function onAsk(e: FormEvent) {
    e.preventDefault()
    const q = question.trim()
    if (q) {
      try {
        sessionStorage.setItem(PENDING_QUESTION_KEY, q)
      } catch {}
    }
    navigate(start)
  }

  return (
    <div className="landing">
      <section className="hero" aria-labelledby="hero-title">
        <div className="hero__map" aria-hidden="true">
          <RegionMap
            interactive={false}
            values={values}
            labels={labels}
            padding={heroPadding}
            drift
            showTowns={!narrow}
          />
        </div>
        <div className="hero__vignette" aria-hidden="true" />

        <header className="hero__nav">
          <span className="hero__brand">Ptej se kraje</span>
          <nav className="hero__links">
            <Link href={user ? routes.map : routes.login}>
              {user ? 'Otevřít mapu' : 'Přihlásit se'}
            </Link>
          </nav>
        </header>

        <div className="hero__copy">
          <h1 id="hero-title">
            Zeptejte se
            <br />
            Plzeňského
            <br />
            kraje.
          </h1>
          <p>
            Napište otázku běžnou češtinou. Odpověď najdeme v otevřených datech a ukážeme ji přímo
            na mapě kraje.
          </p>
          <div className="hero__actions">
            <Link href={start} className="btn btn--primary">
              Začít se ptát
              <Icon name="arrow" size={18} />
            </Link>
            <a href="#series-title" className="btn btn--ghost">
              Ukázky otázek
            </a>
          </div>
        </div>

        <figure className="hero__quote" aria-live="off">
          <blockquote>
            „{demo.q.slice(0, typed)}
            {phase === 'typing' ? <span className="caret" /> : '“'}
          </blockquote>
          <figcaption>
            {shown ? (
              <span key={demo.q} className="hero__answer">
                {shown.text}
                <small>Ukázková data</small>
              </span>
            ) : (
              <span className="hero__wait">
                {phase === 'thinking' ? 'Hledám v otevřených datech…' : '\u00a0'}
              </span>
            )}
          </figcaption>
        </figure>
      </section>

      <section className="series-demo" aria-labelledby="series-title">
        <h2 id="series-title" className="section-title">
          Každá otázka obarví kraj jinak.
        </h2>
        <p className="series-demo__lead">
          Odpovědi se vám skládají do řady malých map. Jedním kliknutím se vrátíte k té, kterou
          potřebujete.
        </p>
        <ol className="series-demo__grid">
          {SAMPLE_CARDS.map((s) => (
            <li key={s.question}>
              <button
                type="button"
                className="series-demo__item"
                onClick={() => askAndStart(s.question)}
              >
                <MiniKraj values={s.values} size={150} tone="dark" />
                <span className="series-demo__metric">{s.answer.metric}</span>
                <span className="series-demo__q">{s.question}</span>
              </button>
            </li>
          ))}
        </ol>
        <p className="series-demo__note">Ukázková data</p>
      </section>

      <section className="how" aria-labelledby="how-title">
        <h2 id="how-title" className="section-title">
          Bez katalogů, tabulek a hledání. Jen otázka.
        </h2>
        <ol className="how__steps">
          <li>
            <h3>Zeptáte se</h3>
            <p>
              Jak byste se zeptali souseda: „Kolik je v okolí školek?“ Žádná znalost datových
              portálů.
            </p>
          </li>
          <li>
            <h3>Najdeme data</h3>
            <p>Asistent vybere vhodnou datovou sadu veřejné správy a spočítá odpověď za vás.</p>
          </li>
          <li>
            <h3>Ukážeme je na mapě</h3>
            <p>Okresy se rozsvítí podle výsledku. U každé odpovědi uvidíte, odkud čísla jsou.</p>
          </li>
        </ol>
      </section>

      <section className="sources" aria-labelledby="sources-title">
        <div className="sources__intro">
          <h2 id="sources-title" className="section-title">
            Každá odpověď má zdroj.
          </h2>
          <p>
            Mapa stojí na ortofotu Českého úřadu zeměměřického a katastrálního a satelitních
            snímcích Copernicus. Odpovědi zatím běží na ukázkových datech, napojení na zdroje níže
            se připravuje.
          </p>
        </div>
        <dl className="sources__list">
          <div>
            <dt>ČÚZK</dt>
            <dd>Ortofoto a hranice kraje a okresů</dd>
            <dd className="sources__state sources__state--live">Používáme</dd>
          </div>
          <div>
            <dt>EOX · Copernicus</dt>
            <dd>Satelitní snímek okolí kraje (Sentinel-2 cloudless)</dd>
            <dd className="sources__state sources__state--live">Používáme</dd>
          </div>
          <div>
            <dt>Český statistický úřad</dt>
            <dd>Obyvatelstvo, bydlení, ekonomika obcí</dd>
            <dd className="sources__state">Připravujeme</dd>
          </div>
          <div>
            <dt>MPSV</dt>
            <dd>Nezaměstnanost a trh práce</dd>
            <dd className="sources__state">Připravujeme</dd>
          </div>
          <div>
            <dt>MŠMT</dt>
            <dd>Rejstřík škol a školských zařízení</dd>
            <dd className="sources__state">Připravujeme</dd>
          </div>
          <div>
            <dt>Národní katalog otevřených dat</dt>
            <dd>Datové sady Plzeňského kraje a obcí</dd>
            <dd className="sources__state">Připravujeme</dd>
          </div>
        </dl>
      </section>

      <section className="close" aria-labelledby="close-title">
        <h2 id="close-title">Na co se zeptáte vy?</h2>
        <form className="close__ask" onSubmit={onAsk}>
          <label htmlFor="close-input" className="sr-only">
            Váš dotaz
          </label>
          <input
            id="close-input"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Třeba: Kde v kraji staví nejvíc bytů?"
            autoComplete="off"
          />
          <button type="submit" aria-label="Položit dotaz">
            <Icon name="send" />
          </button>
        </form>
        <p className="close__note">Po přihlášení dotaz rovnou položíme.</p>
      </section>

      <footer className="foot">
        <span>Ptej se kraje</span>
        <span>Hackathonový projekt nad otevřenými daty Plzeňského kraje</span>
      </footer>
    </div>
  )
}
