import {
  useEffectEvent,
  useLayoutEffect,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type CSSProperties,
} from 'react'
import { AnswerView } from '../chat/AnswerView'
import { SettingsPanel } from '../chat/SettingsPanel'
import { usePreferences } from '../hooks/usePreferences'
import { usePanelResize } from '../hooks/usePanelResize'
import { apiFetch } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { Icon } from '../components/Icon'
import {
  PENDING_QUESTION_KEY,
  SUGGESTIONS,
  ask,
  formatValue,
  normalize,
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
  const inputRef = useRef<HTMLTextAreaElement>(null)
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
  const { preferences, update: updatePreference, reset: resetPreferences } = usePreferences()
  const [popover, setPopover] = useState<Popover>(null)
  const [dataStatus, setDataStatus] = useState('Ověřuji data…')
  useEffect(() => {
    const request = new AbortController()
    apiFetch<{ datasets: { row_count: number; data_kind: string }[] }>('/data/catalog', {
      signal: request.signal,
    })
      .then(({ datasets }) => {
        const loaded = datasets.filter(
          (dataset) => dataset.row_count > 0 && dataset.data_kind !== 'reference',
        )
        setDataStatus(
          !loaded.length
            ? 'Data zatím nejsou načtená'
            : loaded.some((dataset) => dataset.data_kind === 'demo')
              ? 'Ukázková data'
              : 'Data jsou dostupná',
        )
      })
      .catch(() => {
        if (!request.signal.aborted) setDataStatus('Dostupnost dat neověřena')
      })
    return () => request.abort()
  }, [])
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

  const maxPanelWidth = Math.max(330, Math.round(viewport.width * 0.75))
  const panelWidth = Math.max(330, Math.min(preferences.panelWidth, maxPanelWidth))
  const { dragging, handle: resizeHandle } = usePanelResize(panelWidth, maxPanelWidth, (width) =>
    updatePreference('panelWidth', width),
  )
  const expanded = panelWidth >= 560 && !isNarrow
  const maximized = panelWidth >= maxPanelWidth - 2
  function toggleWide() {
    updatePreference('panelWidth', maximized ? 330 : maxPanelWidth)
  }
  const progress = (panelWidth - 330) / Math.max(1, maxPanelWidth - 330)
  const compactInputWidth = Math.min(416, viewport.width - panelWidth - 48)
  const wideInputWidth = Math.min(760, panelWidth - 48)
  const rootStyle = {
    '--panel-width': `${panelWidth}px`,
    '--panel-top': `${16 * (1 - progress)}px`,
    '--panel-bottom': `${80 * (1 - progress)}px`,
    '--composer-left': `${((1 - progress) * (panelWidth + viewport.width)) / 2 + (progress * panelWidth) / 2}px`,
    '--composer-width': `${compactInputWidth * (1 - progress) + wideInputWidth * progress}px`,
  } as CSSProperties
  const behavior =
    preferences.reducedMotion || window.matchMedia('(prefers-reduced-motion: reduce)').matches
      ? 'instant'
      : 'smooth'
  useLayoutEffect(() => {
    if (!inputRef.current) return
    inputRef.current.style.height = 'auto'
    inputRef.current.style.height = `${Math.min(160, inputRef.current.scrollHeight)}px`
  }, [draft])

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
    document.getElementById(`msg-${id}`)?.scrollIntoView({ behavior, block: 'nearest' })
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
        : { top: 32, right: 72, bottom: 96, left: panelWidth + 24 },
    [isNarrow, panelWidth, viewport.height],
  )

  useEffect(() => {
    if (!preferences.autoScroll || (messages.length === 0 && !loading)) return
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior })
  }, [messages, loading, preferences.autoScroll, behavior])

  useEffect(() => {
    if (!popover) return
    const dismiss = (event: PointerEvent) => {
      if (event.target instanceof Element && !event.target.closest('.panel__head')) setPopover(null)
    }
    window.addEventListener('pointerdown', dismiss)
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setPopover(null)
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('pointerdown', dismiss)
    }
  }, [popover])

  const currentRef = useRef(currentId)
  useLayoutEffect(() => {
    currentRef.current = currentId
  }, [currentId])

  async function send(question: string) {
    const q = question.trim()
    if (!q || q.length > 4000 || requestRef.current) return
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
      const answer = await ask(q, messages, request.signal)
      if (request.signal.aborted) return
      const id = uid()
      updateSession(sid, (s) => ({
        ...s,
        messages: [...s.messages, { id, role: 'assistant', answer }],
        activeId: answer.rows ? id : s.activeId,
        updatedAt: Date.now(),
      }))
      if (answer.rows && preferences.autoFocus && currentRef.current === sid) showKraj()
    } catch (err) {
      if (request.signal.aborted) return
      const text = err instanceof Error ? err.message : 'Odpověď se nepodařilo načíst.'
      updateSession(sid, (s) => ({
        ...s,
        messages: [...s.messages, { id: uid(), role: 'error', text, retry: q }],
        updatedAt: Date.now(),
      }))
    } finally {
      if (requestRef.current === request) {
        requestRef.current = null
        setLoadingIn(null)
      }
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
    <div
      className={[
        'app',
        expanded ? 'app--expanded' : '',
        dragging ? 'app--resizing' : '',
        preferences.reducedMotion ? 'app--reduced-motion' : '',
        preferences.textSize === 'large' ? 'app--large-text' : '',
      ]
        .filter(Boolean)
        .join(' ')}
      style={rootStyle}
    >
      <RegionMap
        ref={mapRef}
        values={values}
        labels={preferences.showLabels ? labels : null}
        hovered={hovered}
        onHover={setHovered}
        padding={padding}
        focused={focused}
        viewKey={isNarrow ? 'mobile' : 'desktop'}
        label={
          latest?.metric
            ? `Mapa Plzeňského kraje, okresy obarvené podle: ${latest.metric}`
            : 'Mapa Plzeňského kraje'
        }
        maskOpacity={preferences.dimOutside ? preferences.dimOpacity : 0}
        showTowns={preferences.showTowns}
        basemap={preferences.basemap}
        reducedMotion={preferences.reducedMotion || dragging}
        onSelect={(id) => {
          setFocused(id)
          mapRef.current?.focusOkres(id)
        }}
        className={expanded ? 'region-map--compact' : undefined}
      />
      <div className="app__vignette" aria-hidden="true" />

      <aside
        className={['panel', expanded ? 'panel--wide' : ''].filter(Boolean).join(' ')}
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
          <span className="panel__title">
            Kartogram<span className="panel__status">{dataStatus}</span>
          </span>
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
                aria-label={maximized ? 'Zúžit konverzaci' : 'Rozšířit konverzaci'}
                title={maximized ? 'Zúžit konverzaci' : 'Rozšířit konverzaci'}
                aria-pressed={maximized}
                onClick={toggleWide}
              >
                <Icon name={maximized ? 'collapse' : 'expand'} />
              </button>
            )}
          </div>

          {popover === 'settings' && (
            <SettingsPanel
              preferences={preferences}
              update={updatePreference}
              reset={resetPreferences}
              username={user?.username}
              logout={logout}
            />
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
                    <button
                      type="button"
                      className="suggestion"
                      disabled={Boolean(loadingIn)}
                      onClick={() => send(s)}
                    >
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
                      onAsk={loadingIn ? undefined : (question) => void send(question)}
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
                  <p className="thinking">KartogramMCP hledá v datech</p>
                </li>
              )}
            </ol>
          )}
        </div>
        {!isNarrow && (
          <div
            className="panel__resize"
            role="separator"
            aria-label="Šířka konverzace"
            aria-orientation="vertical"
            aria-valuemin={330}
            aria-valuemax={maxPanelWidth}
            aria-valuenow={Math.round(panelWidth)}
            tabIndex={0}
            title="Tažením změňte šířku · dvojklik rozšíří chat"
            {...resizeHandle}
            onDoubleClick={toggleWide}
          >
            <span />
          </div>
        )}
      </aside>

      <form className="ask" onSubmit={onSubmit}>
        <label htmlFor="ask-input" className="sr-only">
          Dotaz na data Plzeňského kraje
        </label>
        <textarea
          rows={1}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
              event.preventDefault()
              void send(draft)
            }
          }}
          id="ask-input"
          ref={inputRef}
          className="ask__input"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Zeptejte se KartogramMCP…"
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
        {loadingIn && (
          <button
            type="button"
            className="ask__stop"
            aria-label="Zastavit čekání na odpověď"
            onClick={() => {
              requestRef.current?.abort()
              requestRef.current = null
              const sid = loadingIn
              setLoadingIn(null)
              updateSession(sid, (session) => ({
                ...session,
                messages: [
                  ...session.messages,
                  {
                    id: uid(),
                    role: 'error',
                    text: 'Čekání na odpověď bylo zastaveno.',
                    retry:
                      [...session.messages].reverse().find((message) => message.role === 'user')
                        ?.text ?? '',
                  },
                ],
              }))
            }}
          >
            <Icon name="close" size={18} />
          </button>
        )}
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
