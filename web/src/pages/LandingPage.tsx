import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { Icon } from '../components/Icon'
import { PENDING_QUESTION_KEY } from '../chat/assistant'
import { SAMPLES, SAMPLE_DATE } from '../chat/samples'
import { MiniKraj } from '../map/MiniKraj'
import { RegionMap } from '../map/LazyRegionMap'
import type { OkresId } from '../map/geo'
import { navigate, routes } from '../router/router'
import { Link } from '../router/Link'
import { useAuth } from '../auth/AuthContext'
import './LandingPage.css'

const ALL_CATEGORIES = 'Všechna témata'
const CATEGORIES = [ALL_CATEGORIES, ...new Set(SAMPLES.map((sample) => sample.category))]
type HeroPhase = 'question' | 'locating' | 'answer' | 'done'
type HeroPlayback = { phase: HeroPhase; typedQuestion: number; typedAnswer: number }

function initialHeroPlayback(sample: (typeof SAMPLES)[number], complete: boolean): HeroPlayback {
  return {
    phase: complete ? 'done' : 'question',
    typedQuestion: complete ? sample.question.length : 0,
    typedAnswer: complete ? sample.answer.length : 0,
  }
}

export function LandingPage() {
  const { user } = useAuth()
  const reducedMotion = useMemo(
    () => window.matchMedia('(prefers-reduced-motion: reduce)').matches,
    [],
  )
  const [selectedIndex, setSelectedIndex] = useState(0)
  const [playback, setPlayback] = useState<HeroPlayback>(() =>
    initialHeroPlayback(SAMPLES[0], reducedMotion),
  )
  const [category, setCategory] = useState(ALL_CATEGORIES)
  const [question, setQuestion] = useState('')
  const [hovered, setHovered] = useState<OkresId | null>(null)
  const demo = SAMPLES[selectedIndex]
  const visibleSamples = SAMPLES.map((sample, index) => ({ sample, index })).filter(
    ({ sample }) => category === ALL_CATEGORIES || sample.category === category,
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
        ? { top: 90, right: 28, bottom: 400, left: 28 }
        : { top: 120, right: 72, bottom: 72, left: Math.round(window.innerWidth * 0.46) },
    [narrow],
  )

  const start = user ? routes.map : `${routes.login}?registrace`

  useEffect(() => {
    if (reducedMotion) return
    let timer: number
    if (playback.phase === 'question') {
      timer = window.setTimeout(
        () =>
          setPlayback((current) => {
            const typedQuestion = Math.min(current.typedQuestion + 1, demo.question.length)
            return {
              ...current,
              typedQuestion,
              phase: typedQuestion === demo.question.length ? 'locating' : 'question',
            }
          }),
        playback.typedQuestion === 0 ? 500 : 24,
      )
    } else if (playback.phase === 'locating') {
      timer = window.setTimeout(
        () => setPlayback((current) => ({ ...current, phase: 'answer' })),
        1100,
      )
    } else if (playback.phase === 'answer') {
      timer = window.setTimeout(
        () =>
          setPlayback((current) => {
            const typedAnswer = Math.min(current.typedAnswer + 1, demo.answer.length)
            return {
              ...current,
              typedAnswer,
              phase: typedAnswer === demo.answer.length ? 'done' : 'answer',
            }
          }),
        playback.typedAnswer === 0 ? 200 : 20,
      )
    }
    return () => window.clearTimeout(timer)
  }, [demo.answer.length, demo.question.length, playback, reducedMotion])

  function selectSample(index: number) {
    setSelectedIndex(index)
    setPlayback(initialHeroPlayback(SAMPLES[index], reducedMotion))
  }

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
            padding={heroPadding}
            overlay={demo.features}
            overlayKey={playback.phase === 'question' ? undefined : `landing-${selectedIndex}`}
            drift
            hoverable
            hovered={hovered}
            onHover={setHovered}
            showTowns={!narrow}
          />
        </div>
        <div className="hero__vignette" aria-hidden="true" />

        <header className="hero__nav">
          <span className="hero__brand">Kartogram</span>
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
          <div className="hero__exchange" role="group" aria-label="Ukázka dotazu a odpovědi">
            <div className="hero__prompt">
              <span className="hero__prompt-label">Váš dotaz</span>
              <span className="hero__prompt-text">
                {demo.question.slice(0, playback.typedQuestion)}
                {playback.phase === 'question' && <span className="caret" aria-hidden="true" />}
              </span>
            </div>
            {playback.phase === 'locating' && (
              <span className="hero__wait">Hledám parcelu v katastru…</span>
            )}
            {(playback.phase === 'answer' || playback.phase === 'done') && (
              <div className="hero__answer">
                <span>
                  {demo.answer.slice(0, playback.typedAnswer)}
                  {playback.phase === 'answer' && <span className="caret" aria-hidden="true" />}
                </span>
                <small>
                  {demo.source_label} · {SAMPLE_DATE}
                </small>
              </div>
            )}
          </div>
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
      </section>

      <section className="series-demo" aria-labelledby="series-title">
        <h2 id="series-title" className="section-title">
          Začněte tématem, ne datovým katalogem.
        </h2>
        <p className="series-demo__lead">
          Vyberte oblast zájmu a prohlédněte si konkrétní ukázku, její zdroj i omezení. Jde o předem
          načtené veřejné výsledky, ne o živou odpověď na váš dotaz.
        </p>
        <div className="series-demo__categories" role="group" aria-label="Kategorie ukázek">
          {CATEGORIES.map((item) => (
            <button
              key={item}
              type="button"
              aria-pressed={category === item}
              onClick={() => {
                setCategory(item)
                if (item !== ALL_CATEGORIES && demo.category !== item) {
                  const firstMatch = SAMPLES.findIndex((sample) => sample.category === item)
                  if (firstMatch >= 0) selectSample(firstMatch)
                }
              }}
            >
              {item}
            </button>
          ))}
        </div>
        <ol className="series-demo__grid">
          {visibleSamples.map(({ sample, index }) => (
            <li key={sample.question}>
              <button
                type="button"
                className="series-demo__item"
                aria-pressed={selectedIndex === index}
                onClick={() => selectSample(index)}
              >
                <MiniKraj features={sample.features} size={150} tone="dark" />
                <span className="series-demo__metric">{sample.category}</span>
                <span className="series-demo__q">{sample.title}</span>
                <span className="series-demo__question">{sample.question}</span>
              </button>
            </li>
          ))}
        </ol>
        <article className="series-demo__result" aria-live="polite" aria-label="Vybraná ukázka">
          <div>
            <span className="series-demo__metric">{demo.category}</span>
            <h3>{demo.title}</h3>
            <p className="series-demo__result-question">{demo.question}</p>
          </div>
          <div>
            <p>{demo.answer}</p>
            <small>
              {demo.source_label} · Datový snímek {SAMPLE_DATE}
            </small>
            <button
              className="btn btn--primary"
              type="button"
              onClick={() => askAndStart(demo.question)}
            >
              Položit tuto otázku v chatu <Icon name="arrow" size={16} />
            </button>
          </div>
        </article>
        <p className="series-demo__note">
          Kliknutím zobrazíte podrobnosti ukázky. Mapa nahoře ukazuje právě vybranou geometrii.
        </p>
      </section>

      <section className="how" aria-labelledby="how-title">
        <h2 id="how-title" className="section-title">
          Bez katalogů, tabulek a hledání. Jen otázka.
        </h2>
        <ol className="how__steps">
          <li>
            <h3>Zeptáte se</h3>
            <p>
              Třeba: „Leží pozemek v záplavovém území a jaká je dostupnost školy a MHD?“ Bez hledání
              správných vrstev a datových portálů.
            </p>
          </li>
          <li>
            <h3>Najdeme data</h3>
            <p>Asistent vybere vhodnou datovou sadu veřejné správy a spočítá odpověď za vás.</p>
          </li>
          <li>
            <h3>Ukážeme je na mapě</h3>
            <p>
              Parcely, trasy a okolní služby na mapě. Srovnání v grafu nebo tabulce a podklady u
              výsledků.
            </p>
          </li>
        </ol>
      </section>

      <section className="sources" aria-labelledby="sources-title">
        <div className="sources__intro">
          <h2 id="sources-title" className="section-title">
            Každá odpověď má zdroj.
          </h2>
          <p>
            Pracujeme s načtenými daty ČÚZK, ČSÚ, VÚV a AOPK, mapovými údaji OpenStreetMap a
            zastávkami PMDP. U výsledků uvádíme použité podklady a omezení jejich pokrytí.
          </p>
        </div>
        <dl className="sources__list">
          <div>
            <dt>ČÚZK</dt>
            <dd>Ortofoto, adresy, parcely, hranice a občanská vybavenost</dd>
            <dd className="sources__state sources__state--live">Používáme</dd>
          </div>
          <div>
            <dt>EOX · Copernicus</dt>
            <dd>Satelitní snímek okolí kraje (Sentinel-2 cloudless)</dd>
            <dd className="sources__state sources__state--live">Používáme</dd>
          </div>
          <div>
            <dt>Český statistický úřad</dt>
            <dd>Počet obyvatel a věkové složení obcí</dd>
            <dd className="sources__state sources__state--live">Používáme</dd>
          </div>
          <div>
            <dt>VÚV · AOPK</dt>
            <dd>Záplavová a chráněná území</dd>
            <dd className="sources__state sources__state--live">Používáme</dd>
          </div>
          <div>
            <dt>OpenStreetMap</dt>
            <dd>Pěší síť, přechody, komunikace a okolní služby</dd>
            <dd className="sources__state sources__state--live">Používáme</dd>
          </div>
          <div>
            <dt>PMDP</dt>
            <dd>Polohy zastávek městské dopravy</dd>
            <dd className="sources__state sources__state--live">Používáme</dd>
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
            placeholder="Třeba: Prověř parcelu na adrese Koterovská 85, Plzeň na záplavy a chráněná území"
            autoComplete="off"
          />
          <button type="submit" aria-label="Položit dotaz">
            <Icon name="send" />
          </button>
        </form>
        <p className="close__note">Po přihlášení dotaz rovnou položíme.</p>
      </section>

      <footer className="foot">
        <span>Kartogram</span>
        <span>Hackathonový projekt nad otevřenými daty Plzeňského kraje</span>
      </footer>
    </div>
  )
}
