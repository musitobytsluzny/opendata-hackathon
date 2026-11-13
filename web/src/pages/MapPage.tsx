import {
  useEffectEvent,
  useLayoutEffect,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
} from 'react'
import { useAuth } from '../auth/AuthContext'
import { Icon } from '../components/Icon'
import {
  PENDING_QUESTION_KEY,
  SUGGESTIONS,
  ask,
  formatValue,
  normalize,
  okresName,
  type Answer,
  type Message,
} from '../chat/assistant'
import { RegionMap, type RegionMapHandle } from '../map/LazyRegionMap'
import type { OkresId } from '../map/geo'
import './MapPage.css'

const EMPTY_MESSAGES: Message[] = []

type Popover = 'settings' | 'history' | null

const uid = () => `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 7)}`

type Session = {
  id: string
  messages: Message[]
  activeId: string | null
  createdAt: number
  updatedAt: number
}

const newSession = (): Session => {
  const now = Date.now()
  return { id: uid(), messages: [], activeId: null, createdAt: now, updatedAt: now }
}

const storageKey = (user: string | undefined) => `chat_sessions:${user ?? 'anon'}`

function loadSessions(key: string): Session[] {
  try {
    const raw = localStorage.getItem(key)
    const parsed = raw ? (JSON.parse(raw) as Session[]) : []
    return Array.isArray(parsed) ? parsed.filter((s) => s && Array.isArray(s.messages)) : []
  } catch {
    return []
  }
}

function saveSessions(key: string, sessions: Session[]) {
  try {
    localStorage.setItem(
      key,
      JSON.stringify(
        sessions
          .filter((s) => s.messages.length > 0)
          .slice(0, 30)
          .map((s) => ({ ...s, messages: s.messages.slice(-200) })),
      ),
    )
  } catch {
    /* Storage may be disabled or full. */
  }
}

function sessionTitle(s: Session): string {
  const first = s.messages.find((m) => m.role === 'user')
  return first && first.role === 'user' ? first.text : 'Nová konverzace'
}

const timeFormat = new Intl.RelativeTimeFormat('cs', { numeric: 'auto' })
function relativeTime(ts: number): string {
  const diff = (ts - Date.now()) / 1000
  const abs = Math.abs(diff)
  if (abs < 60) return 'právě teď'
  if (abs < 3600) return timeFormat.format(Math.round(diff / 60), 'minute')
  if (abs < 86400) return timeFormat.format(Math.round(diff / 3600), 'hour')
  return timeFormat.format(Math.round(diff / 86400), 'day')
}

export function MapPage() {
  const { user, logout } = useAuth()
  const mapRef = useRef<RegionMapHandle>(null)
  const listRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const key = storageKey(user?.id)
  const [initial] = useState(() => {
    const stored = loadSessions(key)
    const legacy = stored.length ? stored : loadSessions(storageKey(user?.username))
    const sessions = legacy.length ? legacy.slice(0, 30) : [newSession()]
    return { sessions, id: (sessions.find((s) => s.messages.length === 0) ?? sessions[0]).id }
  })
  const [sessions, setSessions] = useState<Session[]>(initial.sessions)
  const [currentId, setCurrentId] = useState(initial.id)
  const requestRef = useRef<AbortController | null>(null)
  useEffect(() => () => requestRef.current?.abort(), [])
  const [loadingIn, setLoadingIn] = useState<string | null>(null)

  const sessionsRef = useRef(sessions)
  useLayoutEffect(() => {
    sessionsRef.current = sessions
  }, [sessions])
  useEffect(() => {
    const timer = window.setTimeout(() => saveSessions(key, sessions), 300)
    return () => window.clearTimeout(timer)
  }, [sessions, key])
  useEffect(() => {
    const persist = () => saveSessions(key, sessionsRef.current)
    window.addEventListener('pagehide', persist)
    return () => {
      window.removeEventListener('pagehide', persist)
      persist()
    }
  }, [key])

  const current = sessions.find((s) => s.id === currentId) ?? null
  const messages = current?.messages ?? EMPTY_MESSAGES
  const activeId = current?.activeId ?? null
  const loading = loadingIn === currentId
  const history = useMemo(
    () => sessions.filter((s) => s.messages.length > 0).sort((a, b) => b.updatedAt - a.updatedAt),
    [sessions],
  )

  function updateSession(id: string, fn: (s: Session) => Session) {
    setSessions((list) => list.map((s) => (s.id === id ? fn(s) : s)))
  }

  function setActiveId(id: string | null) {
    updateSession(currentId, (s) => ({ ...s, activeId: id }))
  }
  const [draft, setDraft] = useState('')
  const [hovered, setHovered] = useState<OkresId | null>(null)
  const [focused, setFocused] = useState<OkresId | null>(null)
  const [wide, setWide] = useState(false)
  const [fading, setFading] = useState(false)
  const fadeTimers = useRef<number[]>([])

  function toggleWide() {
    fadeTimers.current.forEach((t) => window.clearTimeout(t))
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      setWide((w) => !w)
      return
    }
    setFading(true)
    fadeTimers.current = [
      window.setTimeout(() => setWide((w) => !w), 180),
      window.setTimeout(() => setFading(false), 180 + 460),
    ]
  }

  useEffect(() => () => fadeTimers.current.forEach((t) => window.clearTimeout(t)), [])
  const [popover, setPopover] = useState<Popover>(null)
  const [dimOutside, setDimOutside] = useState(true)
  const [isNarrow, setIsNarrow] = useState(() => window.matchMedia('(max-width: 720px)').matches)
  const [viewport, setViewport] = useState(() => ({
    width: window.innerWidth,
    height: window.innerHeight,
  }))

  useEffect(() => {
    let frame = 0
    const on = () => {
      if (frame) return
      frame = requestAnimationFrame(() => {
        frame = 0
        setViewport({ width: window.innerWidth, height: window.innerHeight })
        setIsNarrow(window.matchMedia('(max-width: 720px)').matches)
      })
    }
    window.addEventListener('resize', on)
    return () => {
      window.removeEventListener('resize', on)
      cancelAnimationFrame(frame)
    }
  }, [])

  const expanded = wide && !isNarrow

  const series = useMemo(
    () =>
      messages.flatMap((m) =>
        m.role === 'assistant' && m.answer.rows
          ? [{ id: m.id, answer: m.answer, values: normalize(m.answer.rows) }]
          : [],
      ),
    [messages],
  )

  const active = series.find((s) => s.id === activeId) ?? series[series.length - 1] ?? null
  const latest = active?.answer ?? null

  function showAnswer(id: string) {
    setActiveId(id)
    setHovered(null)
    showKraj()
    document.getElementById(`msg-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }

  function showKraj() {
    setFocused(null)
    mapRef.current?.fitKraj()
  }

  function focusOkres(answerId: string, id: OkresId) {
    if (active?.id !== answerId) setActiveId(answerId)
    if (focused === id) {
      showKraj()
      return
    }
    setFocused(id)
    mapRef.current?.focusOkres(id)
  }

  const values = active?.values ?? null
  const labels = useMemo(
    () =>
      latest?.rows
        ? Object.fromEntries(
            latest.rows.map((r) => [r.okres, formatValue(r.value, latest.unit, latest.signed)]),
          )
        : null,
    [latest],
  )

  const padding = useMemo(
    () =>
      isNarrow
        ? { top: 16, right: 64, bottom: Math.round(viewport.height * 0.45) + 80, left: 16 }
        : expanded
          ? { top: 48, right: 72, bottom: 48, left: Math.round(viewport.width * 0.75) + 24 }
          : { top: 32, right: 88, bottom: 96, left: 370 },
    [isNarrow, expanded, viewport.width, viewport.height],
  )

  useEffect(() => {
    if (messages.length === 0 && !loading) return
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, loading])

  useEffect(() => {
    if (!popover) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setPopover(null)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [popover])

  const currentRef = useRef(currentId)
  useLayoutEffect(() => {
    currentRef.current = currentId
  }, [currentId])

  async function send(question: string) {
    const q = question.trim()
    if (!q || requestRef.current) return
    const request = new AbortController()
    requestRef.current = request
    const sid = currentId
    setDraft('')
    setPopover(null)
    updateSession(sid, (s) => ({
      ...s,
      messages: [...s.messages, { id: uid(), role: 'user', text: q }],
      updatedAt: Date.now(),
    }))
    setLoadingIn(sid)
    try {
      const answer = await ask(q, request.signal)
      if (request.signal.aborted) return
      const id = uid()
      updateSession(sid, (s) => ({
        ...s,
        messages: [...s.messages, { id, role: 'assistant', answer }],
        activeId: answer.rows ? id : s.activeId,
        updatedAt: Date.now(),
      }))
      if (answer.rows && currentRef.current === sid) showKraj()
    } catch (err) {
      if (request.signal.aborted) return
      const text = err instanceof Error ? err.message : 'Odpověď se nepodařilo načíst.'
      updateSession(sid, (s) => ({
        ...s,
        messages: [...s.messages, { id: uid(), role: 'error', text, retry: q }],
        updatedAt: Date.now(),
      }))
    } finally {
      requestRef.current = null
      if (!request.signal.aborted) setLoadingIn(null)
    }
  }

  const sendPending = useEffectEvent((question: string) => {
    void send(question)
  })
  useEffect(() => {
    let active = true
    queueMicrotask(() => {
      if (!active) return
      try {
        const pending = sessionStorage.getItem(PENDING_QUESTION_KEY)
        sessionStorage.removeItem(PENDING_QUESTION_KEY)
        if (pending) sendPending(pending)
      } catch {
        /* Session storage may be disabled. */
      }
    })
    return () => {
      active = false
    }
  }, [])

  function onSubmit(e: FormEvent) {
    e.preventDefault()
    send(draft)
  }

  function resetView() {
    setPopover(null)
    setHovered(null)
    showKraj()
  }

  function newConversation() {
    const empty = sessions.find((s) => s.messages.length === 0)
    if (empty) {
      setCurrentId(empty.id)
    } else {
      const s = newSession()
      setSessions((list) => [s, ...list])
      setCurrentId(s.id)
    }
    resetView()
    inputRef.current?.focus()
  }

  function openSession(id: string) {
    setCurrentId(id)
    setSessions((list) => list.filter((s) => s.id === id || s.messages.length > 0))
    resetView()
  }

  function deleteSession(id: string) {
    const remaining = sessions.filter((session) => session.id !== id)
    const next = remaining.length ? remaining : [newSession()]
    setSessions(next)
    if (id === currentId) {
      setCurrentId(next[0].id)
      resetView()
    }
  }

  return (
    <div className={expanded ? 'app app--expanded' : 'app'}>
      <RegionMap
        ref={mapRef}
        values={values}
        labels={labels}
        hovered={hovered}
        onHover={setHovered}
        padding={padding}
        focused={focused}
        viewKey={isNarrow ? 'mobile' : expanded ? 'expanded' : 'compact'}
        label={
          latest?.metric
            ? `Mapa Plzeňského kraje, okresy obarvené podle: ${latest.metric}`
            : 'Mapa Plzeňského kraje'
        }
        maskOpacity={dimOutside ? 0.68 : 0}
        className={expanded ? 'region-map--compact' : undefined}
      />
      <div className="app__vignette" aria-hidden="true" />

      <aside
        className={['panel', expanded ? 'panel--wide' : '', fading ? 'is-fading' : '']
          .filter(Boolean)
          .join(' ')}
        aria-label="Konverzace"
      >
        <header className="panel__head">
          <button
            type="button"
            className="icon-btn"
            aria-label="Nastavení"
            aria-expanded={popover === 'settings'}
            aria-haspopup="dialog"
            aria-controls={popover === 'settings' ? 'popover-settings' : undefined}
            onClick={() => setPopover(popover === 'settings' ? null : 'settings')}
          >
            <Icon name="settings" />
          </button>
          <span className="panel__title">Ptej se kraje</span>
          <div className="panel__tools" role="toolbar" aria-label="Konverzace">
            <button
              type="button"
              className="icon-btn"
              aria-label="Nová konverzace"
              title="Nová konverzace"
              disabled={messages.length === 0}
              onClick={newConversation}
            >
              <Icon name="plus" />
            </button>
            <button
              type="button"
              className="icon-btn"
              aria-label="Historie konverzací"
              title="Historie konverzací"
              aria-haspopup="dialog"
              aria-expanded={popover === 'history'}
              aria-controls={popover === 'history' ? 'popover-history' : undefined}
              onClick={() => setPopover(popover === 'history' ? null : 'history')}
            >
              <Icon name="history" />
            </button>
            {!isNarrow && (
              <button
                type="button"
                className="icon-btn"
                aria-label={wide ? 'Zúžit konverzaci' : 'Rozšířit konverzaci'}
                title={wide ? 'Zúžit konverzaci' : 'Rozšířit konverzaci'}
                aria-pressed={wide}
                onClick={toggleWide}
              >
                <Icon name={wide ? 'collapse' : 'expand'} />
              </button>
            )}
          </div>

          {popover === 'settings' && (
            <div
              id="popover-settings"
              className="popover popover--left"
              role="dialog"
              aria-label="Nastavení"
            >
              <p className="popover__who">
                Přihlášen jako <strong>{user?.username}</strong>
              </p>
              <label className="switch">
                <input
                  type="checkbox"
                  checked={dimOutside}
                  onChange={(e) => setDimOutside(e.target.checked)}
                />
                <span className="switch__track" aria-hidden="true" />
                Ztmavit okolí kraje
              </label>
              <button type="button" className="popover__item" onClick={logout}>
                <Icon name="logout" size={18} />
                Odhlásit se
              </button>
            </div>
          )}

          {popover === 'history' && (
            <div
              id="popover-history"
              className="popover popover--right"
              role="dialog"
              aria-label="Historie konverzací"
            >
              <p className="popover__heading" id="history-heading">
                Konverzace
              </p>
              {history.length === 0 ? (
                <p className="popover__empty">Zatím tu nejsou žádné konverzace.</p>
              ) : (
                <ul className="popover__list sessions" aria-labelledby="history-heading">
                  {history.map((s) => {
                    const count = s.messages.filter((m) => m.role === 'user').length
                    const isCurrent = s.id === currentId
                    return (
                      <li key={s.id} className={isCurrent ? 'session is-current' : 'session'}>
                        <button
                          type="button"
                          className="session__open"
                          aria-current={isCurrent ? 'true' : undefined}
                          onClick={() => openSession(s.id)}
                        >
                          <span className="session__title">{sessionTitle(s)}</span>
                          <span className="session__meta">
                            {relativeTime(s.updatedAt)} · {count}{' '}
                            {count === 1 ? 'dotaz' : count < 5 ? 'dotazy' : 'dotazů'}
                            {loadingIn === s.id ? ' · odpovídám…' : ''}
                          </span>
                        </button>
                        <button
                          type="button"
                          className="session__delete icon-btn"
                          aria-label={`Smazat konverzaci: ${sessionTitle(s)}`}
                          title="Smazat konverzaci"
                          onClick={() => deleteSession(s.id)}
                        >
                          <Icon name="close" size={16} />
                        </button>
                      </li>
                    )
                  })}
                </ul>
              )}
            </div>
          )}
        </header>

        <div className="panel__body" ref={listRef} aria-live="polite">
          {messages.length === 0 && !loading ? (
            <div className="empty">
              <h1 className="empty__title">Na co se chcete zeptat?</h1>
              <p className="empty__text">
                Ptejte se běžnou češtinou. Odpověď najdu v otevřených datech a ukážu ji na mapě
                kraje.
              </p>
              <ul className="empty__list">
                {SUGGESTIONS.map((s) => (
                  <li key={s}>
                    <button type="button" className="suggestion" onClick={() => send(s)}>
                      <span>{s}</span>
                      <Icon name="arrow" size={16} />
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <ol className="thread" aria-label="Zprávy konverzace">
              {messages.map((m) => (
                <li
                  key={m.id}
                  id={`msg-${m.id}`}
                  className={
                    active?.id === m.id && series.length > 1
                      ? `msg msg--${m.role} msg--active`
                      : `msg msg--${m.role}`
                  }
                >
                  {m.role === 'user' && (
                    <p>
                      <span className="sr-only">Váš dotaz: </span>
                      {m.text}
                    </p>
                  )}
                  {m.role === 'assistant' && (
                    <AnswerView
                      answer={m.answer}
                      hovered={active?.id === m.id ? hovered : null}
                      onHover={active?.id === m.id ? setHovered : () => {}}
                      focused={active?.id === m.id ? focused : null}
                      onFocusOkres={(id) => focusOkres(m.id, id)}
                      onShow={
                        m.answer.rows && active?.id !== m.id ? () => showAnswer(m.id) : undefined
                      }
                    />
                  )}
                  {m.role === 'error' && (
                    <div className="msg__error" role="alert">
                      <p>{m.text}</p>
                      <button type="button" className="text-btn" onClick={() => send(m.retry)}>
                        Zkusit znovu
                      </button>
                    </div>
                  )}
                </li>
              ))}
              {loading && (
                <li className="msg msg--assistant" role="status">
                  <p className="thinking">Hledám v otevřených datech</p>
                </li>
              )}
            </ol>
          )}
        </div>
      </aside>

      <form className="ask" onSubmit={onSubmit}>
        <label htmlFor="ask-input" className="sr-only">
          Dotaz na data Plzeňského kraje
        </label>
        <input
          id="ask-input"
          ref={inputRef}
          className="ask__input"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Zeptejte se na cokoli o kraji…"
          autoComplete="off"
          maxLength={4000}
        />
        <button
          type="submit"
          className="ask__send"
          disabled={!draft.trim() || Boolean(loadingIn)}
          aria-label="Odeslat dotaz"
        >
          {loading ? <span className="spinner" aria-hidden="true" /> : <Icon name="send" />}
        </button>
      </form>

      <div className="map-controls" role="group" aria-label="Ovládání mapy">
        <button
          type="button"
          className="icon-btn"
          aria-label="Přiblížit mapu"
          title="Přiblížit"
          onClick={() => mapRef.current?.zoomIn()}
        >
          <Icon name="plus" />
        </button>
        <button
          type="button"
          className="icon-btn"
          aria-label="Oddálit mapu"
          title="Oddálit"
          onClick={() => mapRef.current?.zoomOut()}
        >
          <Icon name="minus" />
        </button>
        <button
          type="button"
          className="icon-btn"
          aria-label="Vycentrovat mapu na celý kraj"
          title="Vycentrovat mapu na celý kraj"
          onClick={showKraj}
        >
          <Icon name="locate" />
        </button>
      </div>
    </div>
  )
}

function AnswerView({
  answer,
  hovered,
  focused,
  onHover,
  onFocusOkres,
  onShow,
}: {
  answer: Answer
  hovered: OkresId | null
  focused: OkresId | null
  onHover: (id: OkresId | null) => void
  onFocusOkres: (id: OkresId) => void
  onShow?: () => void
}) {
  const max = answer.rows ? Math.max(...answer.rows.map((r) => Math.abs(r.value))) : 1
  return (
    <div className="answer">
      <p>{answer.text}</p>
      {answer.rows && (
        <figure className="answer__data">
          <figcaption>{answer.metric}</figcaption>
          <table className="tabular">
            <caption className="sr-only">
              {answer.metric}. Kliknutím na okres na něj přiblížíte mapu.
            </caption>
            <thead className="sr-only">
              <tr>
                <th scope="col">Okres</th>
                <th scope="col">Poměr</th>
                <th scope="col">Hodnota</th>
              </tr>
            </thead>
            <tbody>
              {answer.rows.map((r) => (
                <tr
                  key={r.okres}
                  className={
                    [
                      hovered === r.okres ? 'is-hovered' : '',
                      focused === r.okres ? 'is-focused' : '',
                    ]
                      .filter(Boolean)
                      .join(' ') || undefined
                  }
                  onMouseEnter={() => onHover(r.okres)}
                  onMouseLeave={() => onHover(null)}
                  onClick={() => onFocusOkres(r.okres)}
                >
                  <th scope="row">
                    <button
                      type="button"
                      className="okres-btn"
                      aria-pressed={focused === r.okres}
                      aria-label={
                        focused === r.okres
                          ? `${okresName(r.okres)}, ${formatValue(r.value, answer.unit, answer.signed)}. Zpět na celý kraj`
                          : `${okresName(r.okres)}, ${formatValue(r.value, answer.unit, answer.signed)}. Přiblížit mapu na okres`
                      }
                      onFocus={() => onHover(r.okres)}
                      onBlur={() => onHover(null)}
                      onClick={(e) => {
                        e.stopPropagation()
                        onFocusOkres(r.okres)
                      }}
                    >
                      {okresName(r.okres)}
                    </button>
                  </th>
                  <td className="answer__bar" aria-hidden="true">
                    <span
                      className={r.value < 0 ? 'bar bar--neg' : 'bar'}
                      style={{ width: `${(Math.abs(r.value) / max) * 100}%` }}
                    />
                  </td>
                  <td className="answer__val">
                    {formatValue(r.value, answer.unit, answer.signed)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </figure>
      )}
      {answer.source && (
        <p className="source">
          <Icon name="database" size={16} />
          <span>
            <span className="sr-only">Zdroj dat: </span>
            {answer.source.publisher} · {answer.source.name} · {answer.source.period}
          </span>
        </p>
      )}
      {onShow && (
        <button type="button" className="show-on-map" onClick={onShow}>
          <Icon name="locate" size={16} />
          Zobrazit na mapě
        </button>
      )}
      {answer.sample && (
        <p className="sample">Ukázková data, napojení na skutečné zdroje se připravuje.</p>
      )}
    </div>
  )
}
