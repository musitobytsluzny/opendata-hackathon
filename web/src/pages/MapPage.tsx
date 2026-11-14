import {
  useEffectEvent,
  useLayoutEffect,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type FormEvent,
} from 'react'
import { useAuth } from '../auth/AuthContext'
import { apiFetch } from '../api/client'
import { Icon } from '../components/Icon'
import { PopoverPortal } from '../components/PopoverPortal'
import { AnswerView } from '../chat/AnswerView'
import { HistoryPanel } from '../chat/HistoryPanel'
import { SettingsPanel } from '../chat/SettingsPanel'
import { PENDING_QUESTION_KEY, SUGGESTIONS, ask, formatValue, normalize } from '../chat/assistant'
import { sessionTitle, uid, useChatSessions, type Session } from '../hooks/useChatSessions'
import { useMapLayers } from '../hooks/useMapLayers'
import type { Artifact } from '../chat/assistant'
import { usePreferences } from '../hooks/usePreferences'
import { useWorkspaceLayout } from '../hooks/useWorkspaceLayout'
import { RegionMap, type RegionMapHandle } from '../map/LazyRegionMap'
import { MapLegend } from '../map/MapLegend'
import type { OkresId } from '../map/geo'
import './MapPage.css'

type Popover = 'settings' | 'history' | null

export function MapPage() {
  const { user, logout } = useAuth()
  const chat = useChatSessions(user?.id, user?.username)
  const { sessions, current, currentId, setCurrentId, update, create, remove, restore } = chat
  const { preferences, update: updatePreference, reset: resetPreferences } = usePreferences()
  const layout = useWorkspaceLayout(preferences.panelWidth, (width) =>
    updatePreference('panelWidth', width),
  )
  const { viewport, mobile, panelWidth, maxWidth, sheetHeight, horizontal, vertical } = layout
  const collapsed = preferences.panelCollapsed
  const dragging = horizontal.dragging || vertical.dragging
  const mapRef = useRef<RegionMapHandle>(null)
  const listRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const requestRef = useRef<AbortController | null>(null)
  const currentRef = useRef(currentId)
  const stickToBottom = useRef(true)
  const scrollPositions = useRef(new Map<string, number>())
  const previouslyCollapsed = useRef(collapsed)
  const lastConversation = useRef(currentId)
  const popoverTrigger = useRef<HTMLElement | null>(null)
  const [loadingIn, setLoadingIn] = useState<string | null>(null)
  const [popover, setPopover] = useState<Popover>(null)
  const [editing, setEditing] = useState<{ id: string; previousDraft: string } | null>(null)
  const [hovered, setHovered] = useState<OkresId | null>(null)
  const [focused, setFocused] = useState<OkresId | null>(null)
  const [awayFromBottom, setAwayFromBottom] = useState(false)
  const [unread, setUnread] = useState(false)
  const [deleted, setDeleted] = useState<Session | null>(null)
  const [dataStatus, setDataStatus] = useState('Ověřuji data…')
  const [fullScreen, setFullScreen] = useState(Boolean(document.fullscreenElement))
  const parcelRequest = useRef<AbortController | null>(null)
  const [mapInteraction, setMapInteraction] = useState<{
    session: string
    mode: 'navigate' | 'parcel' | 'compare'
  }>({ session: currentId, mode: 'navigate' })
  const mapMode = mapInteraction.session === currentId ? mapInteraction.mode : 'navigate'
  function setMapMode(mode: 'navigate' | 'parcel' | 'compare') {
    parcelRequest.current?.abort()
    workspace.clear()
    setParcelSelection({ session: currentId, items: [] })
    setMapInteraction({ session: currentId, mode })
  }
  const [parcelFeedback, setParcelFeedback] = useState({ session: currentId, text: '' })
  const parcelStatus = parcelFeedback.session === currentId ? parcelFeedback.text : ''
  function setParcelStatus(text: string) {
    setParcelFeedback({ session: currentId, text })
  }
  const [parcelSelection, setParcelSelection] = useState<{
    session: string
    items: { number: string; ku: string; artifact: Artifact }[]
  }>({ session: currentId, items: [] })
  const [selectionSession, setSelectionSession] = useState(currentId)
  if (selectionSession !== currentId) {
    setSelectionSession(currentId)
    setMapInteraction({ session: currentId, mode: 'navigate' })
    setParcelSelection({ session: currentId, items: [] })
    setParcelFeedback({ session: currentId, text: '' })
  }
  useEffect(() => () => parcelRequest.current?.abort(), [])
  useEffect(() => {
    parcelRequest.current?.abort()
  }, [currentId])
  const messages = current.messages
  const workspace = useMapLayers(messages, currentId)
  const selectedParcels = parcelSelection.session === currentId ? parcelSelection.items : []
  async function selectParcel(lon: number, lat: number) {
    if (mapMode === 'navigate') return
    if (mapMode === 'parcel' || selectedParcels.length >= 2) {
      workspace.clear()
      setParcelSelection({ session: currentId, items: [] })
    }
    parcelRequest.current?.abort()
    const request = new AbortController()
    parcelRequest.current = request
    const sessionId = currentId
    setParcelStatus('Hledám parcelu v katastru…')
    try {
      const { result } = await apiFetch<{ result: Artifact }>(
        `/data/parcels/at-point?lat=${lat}&lon=${lon}`,
        { signal: request.signal },
      )
      if (request.signal.aborted || currentRef.current !== sessionId) return
      if (!result.rows.length) {
        setParcelStatus('V tomto místě nebyla nalezena parcela.')
        return
      }
      update(sessionId, (session) => ({
        ...session,
        messages: [
          ...session.messages,
          {
            id: uid(),
            role: 'assistant',
            answer: {
              text:
                result.rows.length === 1
                  ? 'Vybraná parcela z mapy.'
                  : 'Kliknutí odpovídá více parcelám. Pro jednoznačný výběr klikněte dovnitř parcely.',
              sample: result.sample,
              artifacts: [{ ...result, view: 'table' }],
            },
          },
        ],
        updatedAt: Date.now(),
      }))
      if (result.rows.length !== 1) {
        workspace.show(result)
        setParcelStatus('Na hranici je více parcel. Klikněte dovnitř konkrétní parcely.')
        return
      }
      const row = result.rows[0]
      const selection = { number: String(row.name), ku: String(row.kod_ku), artifact: result }
      const previous =
        mapMode === 'compare' &&
        parcelSelection.session === sessionId &&
        parcelSelection.items.length < 2
          ? parcelSelection.items
          : []
      const items = [
        ...previous.filter((item) => item.number !== selection.number || item.ku !== selection.ku),
        selection,
      ].slice(-2)
      workspace.showSelection(items.map((item) => item.artifact))
      setParcelSelection({ session: sessionId, items })
      setParcelStatus(
        mapMode === 'compare'
          ? `Vybráno ${items.length}/2 parcel.`
          : `Parcela ${selection.number}, KÚ ${selection.ku}.`,
      )
    } catch (error) {
      if (!request.signal.aborted && currentRef.current === sessionId)
        setParcelStatus(error instanceof Error ? error.message : 'Parcelu se nepodařilo načíst.')
    }
  }
  const draft = current.draft ?? ''
  const loading = loadingIn === currentId
  const motion =
    preferences.reducedMotion || window.matchMedia('(prefers-reduced-motion: reduce)').matches
  const behavior = motion ? 'instant' : 'smooth'
  const denseMap = mobile && !collapsed && sheetHeight > viewport.height * 0.73
  const expanded = !mobile && panelWidth >= 560
  const maximized = panelWidth >= maxWidth - 2
  const progress = Math.max(0, Math.min(1, (panelWidth - 330) / Math.max(1, maxWidth - 330)))
  const compactWidth = Math.min(416, viewport.width - panelWidth - 48)
  const rootStyle = {
    '--panel-width': `${panelWidth}px`,
    '--panel-progress': progress,
    '--panel-top': `${16 * (1 - progress)}px`,
    '--panel-bottom': `${80 * (1 - progress)}px`,
    '--composer-left': `${((1 - progress) * (panelWidth + viewport.width)) / 2 + (progress * panelWidth) / 2}px`,
    '--composer-width': `${compactWidth * (1 - progress) + Math.min(760, panelWidth - 48) * progress}px`,
    '--sheet-height': `${sheetHeight}px`,
    '--viewport-height': `${viewport.height}px`,
    '--viewport-top': `${viewport.top}px`,
  } as CSSProperties

  useLayoutEffect(() => {
    currentRef.current = currentId
  }, [currentId])
  useEffect(() => () => requestRef.current?.abort(), [])
  useEffect(() => {
    const request = new AbortController()
    apiFetch<{ datasets: { row_count: number; data_kind: string }[] }>('/data/catalog', {
      signal: request.signal,
    })
      .then(({ datasets }) => {
        if (request.signal.aborted) return
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
  useEffect(() => {
    if (!deleted) return
    const timer = window.setTimeout(() => setDeleted(null), 8000)
    return () => window.clearTimeout(timer)
  }, [deleted])
  useEffect(() => {
    const onChange = () => setFullScreen(Boolean(document.fullscreenElement))
    document.addEventListener('fullscreenchange', onChange)
    return () => document.removeEventListener('fullscreenchange', onChange)
  }, [])
  useLayoutEffect(() => {
    const input = inputRef.current
    if (!input) return
    input.style.height = 'auto'
    input.style.height = `${Math.min(144, input.scrollHeight)}px`
  }, [draft, collapsed, panelWidth, mobile])

  function setDraft(text: string) {
    update(currentId, (session) => ({ ...session, draft: text }))
  }
  function toggleWide() {
    updatePreference('panelWidth', maximized ? 330 : maxWidth)
  }
  function openComposer() {
    updatePreference('panelCollapsed', false)
    requestAnimationFrame(() => inputRef.current?.focus())
  }
  function closePopover() {
    setPopover(null)
    popoverTrigger.current?.focus()
  }
  function togglePopover(next: Exclude<Popover, null>) {
    popoverTrigger.current =
      document.activeElement instanceof HTMLElement ? document.activeElement : null
    setPopover((previous) => (previous === next ? null : next))
  }
  useEffect(() => {
    if (!popover || collapsed) return
    const timer = window.setTimeout(() => {
      document
        .querySelector<HTMLElement>(
          popover === 'history' ? '#popover-history input' : '#popover-settings input',
        )
        ?.focus()
    }, 0)
    const dismiss = (event: PointerEvent) => {
      if (event.target instanceof Element && !event.target.closest('.panel__head, .popover'))
        setPopover(null)
    }
    window.addEventListener('pointerdown', dismiss)
    return () => {
      window.clearTimeout(timer)
      window.removeEventListener('pointerdown', dismiss)
    }
  }, [popover, collapsed])

  const series = useMemo(
    () =>
      messages.flatMap((message) =>
        message.role === 'assistant' && message.answer.rows?.length
          ? [{ id: message.id, answer: message.answer, values: normalize(message.answer.rows) }]
          : [],
      ),
    [messages],
  )
  const active = series.find((item) => item.id === current.activeId) ?? series.at(-1) ?? null
  const latest = active?.answer ?? null
  const labels = useMemo(
    () =>
      latest?.rows
        ? Object.fromEntries(
            latest.rows.map((row) => [
              row.okres,
              formatValue(row.value, latest.unit, latest.signed),
            ]),
          )
        : null,
    [latest],
  )
  const padding = useMemo(
    () =>
      mobile
        ? { top: 56, right: 56, bottom: collapsed ? 88 : Math.round(sheetHeight) + 24, left: 24 }
        : { top: 64, right: 88, bottom: 80, left: collapsed ? 48 : panelWidth + 48 },
    [mobile, collapsed, panelWidth, sheetHeight],
  )

  function showKraj() {
    setFocused(null)
    mapRef.current?.fitKraj()
  }
  function showAnswer(id: string) {
    update(currentId, (session) => ({ ...session, activeId: id }))
    setHovered(null)
    showKraj()
    document.getElementById(`msg-${id}`)?.scrollIntoView({ behavior, block: 'nearest' })
  }
  function focusOkres(answerId: string, id: OkresId) {
    if (active?.id !== answerId)
      update(currentId, (session) => ({ ...session, activeId: answerId }))
    if (focused === id) {
      showKraj()
      return
    }
    setFocused(id)
    mapRef.current?.focusOkres(id)
  }
  function scrollToLatest(smooth = true) {
    stickToBottom.current = true
    setUnread(false)
    listRef.current?.scrollTo({
      top: listRef.current.scrollHeight,
      behavior: smooth ? behavior : 'instant',
    })
  }
  const syncScroll = useEffectEvent(() => {
    const reopening = previouslyCollapsed.current && !collapsed
    previouslyCollapsed.current = collapsed
    const switched = lastConversation.current !== currentId
    if (switched) {
      lastConversation.current = currentId
      stickToBottom.current = true
      setUnread(false)
      setAwayFromBottom(false)
    }
    if (collapsed) return
    if (reopening && !stickToBottom.current && listRef.current)
      listRef.current.scrollTop = scrollPositions.current.get(currentId) ?? 0
    if (preferences.autoScroll && stickToBottom.current) scrollToLatest(false)
    else if (messages.length) setUnread(true)
  })
  useLayoutEffect(() => {
    const frame = requestAnimationFrame(() => syncScroll())
    return () => cancelAnimationFrame(frame)
  }, [messages, loading, currentId, collapsed, preferences.autoScroll])

  function cancelEdit() {
    if (editing) setDraft(editing.previousDraft)
    setEditing(null)
  }
  function editQuestion(id: string) {
    const message = messages.find((item) => item.id === id)
    if (message?.role !== 'user' || loadingIn) return
    setEditing({ id, previousDraft: editing?.previousDraft ?? draft })
    setDraft(message.text)
    openComposer()
  }
  async function send(question: string) {
    const q = question.trim()
    if (!q || q.length > 4000 || requestRef.current) return
    const request = new AbortController()
    requestRef.current = request
    let sid = currentId
    let context = messages
    if (editing) {
      const index = messages.findIndex((message) => message.id === editing.id)
      if (index >= 0) {
        context = messages.slice(0, index)
        update(currentId, (session) => ({ ...session, draft: editing.previousDraft }))
        sid = create(context)
        update(sid, (session) => ({ ...session, title: q.slice(0, 100) }))
      }
      setEditing(null)
    }
    update(sid, (session) => ({
      ...session,
      draft: '',
      messages: [...session.messages, { id: uid(), role: 'user', text: q }],
      updatedAt: Date.now(),
    }))
    setPopover(null)
    stickToBottom.current = true
    setLoadingIn(sid)
    try {
      const answer = await ask(q, context, request.signal)
      if (request.signal.aborted) return
      const id = uid()
      update(sid, (session) => ({
        ...session,
        messages: [...session.messages, { id, role: 'assistant', answer }],
        activeId: answer.rows?.length ? id : session.activeId,
        updatedAt: Date.now(),
      }))
      if (preferences.autoFocus && currentRef.current === sid) {
        const chart = answer.artifacts?.some((item) => item.view === 'bar' || item.view === 'line')
        const mapResult = answer.artifacts?.some(
          (item) => item.view === 'map' && item.features.length,
        )
        if (chart || mapResult) {
          updatePreference('panelCollapsed', false)
          if (mobile) layout.focusContent(chart ? 'chart' : 'map')
          else updatePreference('panelWidth', chart ? Math.min(maxWidth, 760) : 330)
          requestAnimationFrame(() =>
            requestAnimationFrame(() => {
              if (currentRef.current !== sid) return
              const element = document.querySelector<HTMLElement>(`#msg-${id} .result-view`)
              element?.scrollIntoView({ behavior, block: 'nearest' })
              if (chart && element) {
                element.tabIndex = -1
                element.focus({ preventScroll: true })
              }
            }),
          )
        } else if (answer.rows?.length) showKraj()
      }
    } catch (error) {
      if (request.signal.aborted) return
      const text = error instanceof Error ? error.message : 'Odpověď se nepodařilo načíst.'
      update(sid, (session) => ({
        ...session,
        messages: [...session.messages, { id: uid(), role: 'error', text, retry: q }],
        updatedAt: Date.now(),
      }))
    } finally {
      if (requestRef.current === request) {
        requestRef.current = null
        setLoadingIn(null)
      }
    }
  }
  function stopWaiting(record = true) {
    const sid = loadingIn
    requestRef.current?.abort()
    requestRef.current = null
    setLoadingIn(null)
    if (sid && record)
      update(sid, (session) => ({
        ...session,
        messages: [
          ...session.messages,
          {
            id: uid(),
            role: 'error',
            text: 'Čekání na odpověď bylo zastaveno.',
            retry: session.messages.findLast((message) => message.role === 'user')?.text ?? '',
          },
        ],
      }))
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
        /* Session storage is optional. */
      }
    })
    return () => {
      active = false
    }
  }, [])
  const shortcut = useEffectEvent((event: KeyboardEvent) => {
    const input =
      event.target instanceof Element &&
      event.target.closest('input, textarea, select, [contenteditable="true"]')
    if (event.key === '/' && !input && !event.metaKey && !event.ctrlKey && !event.altKey) {
      event.preventDefault()
      openComposer()
    }
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
      event.preventDefault()
      updatePreference('panelCollapsed', false)
      setPopover('history')
    }
    if (event.key === 'Escape') {
      if (popover) closePopover()
      else if (editing) cancelEdit()
      else {
        updatePreference('panelCollapsed', true)
        inputRef.current?.blur()
      }
    }
  })
  useEffect(() => {
    window.addEventListener('keydown', shortcut)
    return () => window.removeEventListener('keydown', shortcut)
  }, [])

  function resetView() {
    setPopover(null)
    setHovered(null)
    showKraj()
  }
  function newConversation() {
    cancelEdit()
    const empty = sessions.find((session) => !session.messages.length && !session.draft?.trim())
    if (empty) setCurrentId(empty.id)
    else create()
    resetView()
    openComposer()
  }
  function openSession(id: string) {
    cancelEdit()
    setCurrentId(id)
    resetView()
  }
  function deleteSession(id: string) {
    const session = sessions.find((item) => item.id === id)
    if (!session) return
    if (loadingIn === id) stopWaiting(false)
    if (currentId === id) {
      setEditing(null)
      resetView()
    }
    setDeleted(session)
    remove(id)
  }
  function exportConversation() {
    const text = [
      `# ${sessionTitle(current)}`,
      '',
      'Kartogram · export konverzace',
      '',
      ...messages.flatMap((message) => [
        `## ${message.role === 'user' ? 'Vy' : message.role === 'assistant' ? 'KartogramMCP' : 'Chyba'}`,
        '',
        message.role === 'assistant'
          ? message.answer.text +
            (message.answer.source
              ? `\n\nZdroj: ${message.answer.source.publisher} · ${message.answer.source.period}`
              : '') +
            (message.answer.sample ? '\n\nUkázková data.' : '')
          : message.text,
        '',
      ]),
    ].join('\n')
    const url = URL.createObjectURL(new Blob([text], { type: 'text/markdown;charset=utf-8' }))
    const link = document.createElement('a')
    link.href = url
    link.download = 'kartogram-konverzace.md'
    link.click()
    window.setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
  function onSubmit(event: FormEvent) {
    event.preventDefault()
    void send(draft)
  }

  return (
    <div
      className={[
        'app',
        collapsed ? 'app--collapsed' : '',
        expanded ? 'app--expanded' : '',
        dragging ? 'app--resizing' : '',
        motion ? 'app--reduced-motion' : '',
        preferences.textSize === 'large' ? 'app--large-text' : '',
      ]
        .filter(Boolean)
        .join(' ')}
      style={rootStyle}
    >
      <RegionMap
        ref={mapRef}
        overlay={workspace.features}
        focusFeatures={workspace.focusFeatures}
        overlayKey={workspace.focusKey}
        onMapClick={mapMode === 'navigate' ? undefined : (lon, lat) => void selectParcel(lon, lat)}
        values={active?.values ?? null}
        labels={preferences.showLabels ? labels : null}
        hovered={hovered}
        onHover={setHovered}
        padding={padding}
        focused={focused}
        viewKey={mobile ? 'mobile' : 'desktop'}
        className={expanded ? 'region-map--compact' : undefined}
        label={
          latest?.metric
            ? `Mapa Plzeňského kraje, okresy obarvené podle: ${latest.metric}`
            : 'Mapa Plzeňského kraje'
        }
        maskOpacity={preferences.dimOutside ? preferences.dimOpacity : 0}
        showTowns={preferences.showTowns}
        basemap={preferences.basemap}
        palette={preferences.palette}
        reducedMotion={motion || dragging}
        onSelect={(id) => {
          if (focused === id) showKraj()
          else {
            setFocused(id)
            mapRef.current?.focusOkres(id)
          }
        }}
      />
      <div className="app__vignette" aria-hidden="true" />
      <details className="map-layers" open={mapMode !== 'navigate' || undefined}>
        <summary>
          Mapa a vrstvy{workspace.layers.length ? ` · ${workspace.layers.length}` : ''}
        </summary>
        {workspace.layers.map((layer) => (
          <label key={layer.artifact.result_id}>
            <input
              type="checkbox"
              checked={layer.visible}
              onChange={(event) => workspace.toggle(layer.artifact.result_id, event.target.checked)}
            />
            <span style={{ color: layer.color }}>{layer.artifact.title}</span>
          </label>
        ))}
        <div className="map-layers__tools">
          <button
            type="button"
            aria-pressed={mapMode === 'navigate'}
            onClick={() => {
              setMapMode('navigate')
              parcelRequest.current?.abort()
              setParcelStatus('')
            }}
          >
            Pohyb mapy
          </button>
          <button
            type="button"
            aria-pressed={mapMode === 'parcel'}
            onClick={() => {
              setMapMode('parcel')
              setParcelStatus('Klikněte na parcelu v mapě.')
              setParcelSelection({ session: currentId, items: [] })
            }}
          >
            Vybrat parcelu
          </button>
          <button
            type="button"
            aria-pressed={mapMode === 'compare'}
            onClick={() => {
              setMapMode('compare')
              setParcelStatus('Klikněte na dvě parcely.')
              setParcelSelection({ session: currentId, items: [] })
            }}
          >
            Porovnat parcely
          </button>
        </div>
        {parcelStatus && (
          <p className="map-layers__status" role="status">
            {parcelStatus}
          </p>
        )}
        {selectedParcels.length > 0 && (
          <div className="map-layers__tools">
            <button
              type="button"
              disabled={Boolean(loadingIn) || (mapMode === 'compare' && selectedParcels.length < 2)}
              onClick={() =>
                void send(
                  selectedParcels.length === 2
                    ? `Porovnej parcely ${selectedParcels.map((item) => `číslo ${item.number} v katastrálním území s kódem ${item.ku}`).join(' a ')}. Použij skutečné údaje, prověř obě parcely a shrň rozdíly i chybějící data.`
                    : `Prověř parcelu číslo ${selectedParcels[0].number} v katastrálním území s kódem ${selectedParcels[0].ku}, kterou jsem vybral na mapě.`,
                )
              }
            >
              {selectedParcels.length === 2 ? 'Porovnat v chatu' : 'Prověřit v chatu'}
            </button>
          </div>
        )}
      </details>

      {collapsed ? (
        <div className="chat-launcher">
          <button
            type="button"
            className="chat-launcher__open"
            onClick={openComposer}
            aria-label="Otevřít konverzaci"
          >
            <span>
              <strong>Kartogram</strong>
              <small>{loadingIn ? 'KartogramMCP odpovídá…' : 'Otevřít konverzaci'}</small>
            </span>
            <Icon name={mobile ? 'chevronUp' : 'expand'} size={18} />
          </button>
          <button
            type="button"
            className="icon-btn"
            aria-label="Nová konverzace"
            title="Nová konverzace"
            onClick={newConversation}
          >
            <Icon name="plus" />
          </button>
        </div>
      ) : (
        <aside className={`panel${expanded ? ' panel--wide' : ''}`} aria-label="Konverzace">
          {mobile && (
            <div
              className="panel__sheet-handle"
              role="separator"
              aria-label="Výška konverzace"
              aria-orientation="horizontal"
              aria-valuemin={Math.round(layout.minHeight)}
              aria-valuemax={Math.round(layout.maxHeight)}
              aria-valuenow={Math.round(sheetHeight)}
              tabIndex={0}
              {...vertical.handle}
              onDoubleClick={layout.toggleSheet}
            >
              <span />
            </div>
          )}
          <header className="panel__head">
            <div className="panel__brand">
              <span className="panel__title">
                Kartogram<span className="panel__status">{dataStatus}</span>
              </span>
            </div>
            <div className="panel__tools" role="toolbar" aria-label="Konverzace">
              <button
                type="button"
                className="icon-btn"
                aria-label="Nová konverzace"
                title="Nová konverzace"
                onClick={newConversation}
              >
                <Icon name="plus" size={18} />
              </button>
              <button
                type="button"
                className="icon-btn"
                aria-label="Historie konverzací"
                title="Historie · ⌘/Ctrl K"
                aria-expanded={popover === 'history'}
                aria-haspopup="dialog"
                onClick={() => togglePopover('history')}
              >
                <Icon name="history" size={18} />
              </button>
              <button
                type="button"
                className="icon-btn"
                aria-label="Nastavení"
                title="Nastavení"
                aria-expanded={popover === 'settings'}
                aria-haspopup="dialog"
                onClick={() => togglePopover('settings')}
              >
                <Icon name="settings" size={18} />
              </button>
              <button
                type="button"
                className="icon-btn"
                aria-label={
                  mobile
                    ? 'Změnit výšku konverzace'
                    : maximized
                      ? 'Zúžit konverzaci'
                      : 'Rozšířit konverzaci'
                }
                title={mobile ? 'Změnit výšku panelu' : 'Rozšířit / zúžit'}
                aria-pressed={mobile ? sheetHeight > viewport.height * 0.7 : maximized}
                onClick={mobile ? layout.toggleSheet : toggleWide}
              >
                <Icon name={maximized ? 'collapse' : 'expand'} size={18} />
              </button>
              <button
                type="button"
                className="icon-btn"
                aria-label="Sbalit konverzaci"
                title="Sbalit · Esc"
                onClick={() => {
                  setPopover(null)
                  updatePreference('panelCollapsed', true)
                }}
              >
                <Icon name={mobile ? 'chevronDown' : 'minus'} size={18} />
              </button>
            </div>
            {popover === 'settings' && (
              <PopoverPortal>
                <SettingsPanel
                  preferences={preferences}
                  update={updatePreference}
                  reset={resetPreferences}
                  username={user?.username}
                  logout={logout}
                  hasHistory={sessions.some(
                    (session) => session.messages.length > 0 || session.draft?.trim(),
                  )}
                  onClearHistory={() => {
                    stopWaiting(false)
                    setEditing(null)
                    setDeleted(null)
                    chat.clear()
                    resetView()
                  }}
                />
              </PopoverPortal>
            )}
            {popover === 'history' && (
              <PopoverPortal>
                <HistoryPanel
                  sessions={sessions}
                  currentId={currentId}
                  loadingIn={loadingIn}
                  onOpen={openSession}
                  onDelete={deleteSession}
                  onRename={(id, title) => update(id, (session) => ({ ...session, title }))}
                  onPin={(id) => update(id, (session) => ({ ...session, pinned: !session.pinned }))}
                  onExport={exportConversation}
                />
              </PopoverPortal>
            )}
          </header>
          <div
            className="panel__body"
            ref={listRef}
            role="log"
            aria-label="Zprávy konverzace"
            aria-live="polite"
            onScroll={() => {
              const list = listRef.current
              if (!list) return
              const away = list.scrollHeight - list.scrollTop - list.clientHeight > 64
              scrollPositions.current.set(currentId, list.scrollTop)
              stickToBottom.current = !away
              setAwayFromBottom(away)
              if (!away) setUnread(false)
            }}
          >
            {!messages.length && !loading ? (
              <div className="empty">
                <h1 className="empty__title">Na co se chcete zeptat?</h1>
                <p className="empty__text">
                  Ptejte se běžnou češtinou. Odpověď najdu v otevřených datech a ukážu ji na mapě
                  kraje.
                </p>
                <ul className="empty__list">
                  {SUGGESTIONS.map((question) => (
                    <li key={question}>
                      <button
                        type="button"
                        className="suggestion"
                        disabled={Boolean(loadingIn)}
                        onClick={() => void send(question)}
                      >
                        <span>{question}</span>
                        <Icon name="arrow" size={16} />
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ) : (
              <ol className="thread">
                {messages.map((message) => (
                  <li
                    key={message.id}
                    id={`msg-${message.id}`}
                    className={`msg msg--${message.role}${active?.id === message.id && series.length > 1 ? ' msg--active' : ''}`}
                  >
                    {message.role === 'user' && (
                      <div className="user-message">
                        <div className="user-message__label">
                          <button
                            type="button"
                            className="icon-btn"
                            aria-label={`Upravit dotaz: ${message.text}`}
                            title="Upravit a odeslat znovu"
                            disabled={Boolean(loadingIn)}
                            onClick={() => editQuestion(message.id)}
                          >
                            <Icon name="edit" size={14} />
                          </button>
                        </div>
                        <p>{message.text}</p>
                      </div>
                    )}
                    {message.role === 'assistant' && (
                      <AnswerView
                        answer={message.answer}
                        onMap={workspace.show}
                        onAsk={loadingIn ? undefined : (question) => void send(question)}
                        hovered={active?.id === message.id ? hovered : null}
                        onHover={active?.id === message.id ? setHovered : () => {}}
                        focused={active?.id === message.id ? focused : null}
                        onFocusOkres={(id) => focusOkres(message.id, id)}
                        onShow={
                          message.answer.rows?.length && active?.id !== message.id
                            ? () => showAnswer(message.id)
                            : undefined
                        }
                      />
                    )}
                    {message.role === 'error' && (
                      <div className="msg__error" role="alert">
                        <p>{message.text}</p>
                        <button
                          type="button"
                          className="text-btn"
                          disabled={Boolean(loadingIn)}
                          onClick={() => void send(message.retry)}
                        >
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
          {(awayFromBottom || unread) && (
            <button type="button" className="jump-latest" onClick={() => scrollToLatest()}>
              <Icon name="chevronDown" size={14} />
              {unread ? 'Nové zprávy' : 'Nejnovější zprávy'}
            </button>
          )}
          {!mobile && (
            <div
              className="panel__resize"
              role="separator"
              aria-label="Šířka konverzace"
              aria-orientation="vertical"
              aria-valuemin={330}
              aria-valuemax={maxWidth}
              aria-valuenow={Math.round(panelWidth)}
              tabIndex={0}
              {...horizontal.handle}
              title="Táhněte pro změnu šířky · dvojklik rozšíří"
              onDoubleClick={toggleWide}
            >
              <span />
            </div>
          )}
        </aside>
      )}

      {!collapsed && (
        <div className="composer-dock">
          {editing && (
            <div className="edit-banner">
              <span>
                <strong>Upravujete dřívější dotaz</strong>Původní konverzace zůstane v historii.
              </span>
              <button
                type="button"
                className="icon-btn"
                aria-label="Zrušit úpravu dotazu"
                onClick={cancelEdit}
              >
                <Icon name="close" size={16} />
              </button>
            </div>
          )}
          {loadingIn && !loading && (
            <p className="composer-note">Odpověď se dokončuje v jiné konverzaci.</p>
          )}
          <form className="ask" onSubmit={onSubmit}>
            <label htmlFor="ask-input" className="sr-only">
              Dotaz na data Plzeňského kraje
            </label>
            <textarea
              id="ask-input"
              ref={inputRef}
              className="ask__input"
              rows={1}
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              placeholder={editing ? 'Upravte svůj dotaz…' : 'Zeptejte se KartogramMCP…'}
              autoComplete="off"
              maxLength={4000}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
                  event.preventDefault()
                  void send(draft)
                }
              }}
            />
            {loadingIn ? (
              <button
                type="button"
                className="ask__send ask__stop"
                aria-label="Zastavit čekání na odpověď"
                title="Zastavit čekání"
                onClick={() => stopWaiting()}
              >
                <span />
              </button>
            ) : (
              <button
                type="submit"
                className="ask__send"
                disabled={!draft.trim()}
                aria-label={editing ? 'Odeslat upravený dotaz' : 'Odeslat dotaz'}
              >
                <Icon name="send" size={18} />
              </button>
            )}
          </form>
          {draft.length > 3200 && <span className="composer-count">{draft.length}/4000</span>}
        </div>
      )}

      {latest && preferences.showLegend && !denseMap && (
        <MapLegend
          answer={latest}
          focused={focused}
          onReset={showKraj}
          onHide={() => updatePreference('showLegend', false)}
        />
      )}
      {latest && (!preferences.showLegend || denseMap) && (
        <button
          type="button"
          className="legend-launcher"
          onClick={() => {
            updatePreference('showLegend', true)
            if (denseMap) layout.toggleSheet()
          }}
        >
          <Icon name="database" size={14} />
          Legenda
        </button>
      )}
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
        <div className="map-controls__rule" />
        <button
          type="button"
          className="icon-btn"
          aria-label="Vycentrovat mapu na celý kraj"
          title="Celý kraj"
          onClick={showKraj}
        >
          <Icon name="locate" />
        </button>
        {document.fullscreenEnabled && (
          <button
            type="button"
            className="icon-btn"
            aria-label={fullScreen ? 'Ukončit celou obrazovku' : 'Celá obrazovka'}
            title="Celá obrazovka"
            onClick={() => {
              const action = document.fullscreenElement
                ? document.exitFullscreen()
                : document.documentElement.requestFullscreen()
              void action.catch(() => {})
            }}
          >
            <Icon name="frame" size={18} />
          </button>
        )}
      </div>
      {deleted && (
        <div className="workspace-toast" role="status">
          Konverzace smazána.
          <button
            type="button"
            onClick={() => {
              restore(deleted)
              setDeleted(null)
              setEditing(null)
              resetView()
            }}
          >
            Vrátit
          </button>
          <button
            type="button"
            className="icon-btn"
            aria-label="Zavřít oznámení"
            onClick={() => setDeleted(null)}
          >
            <Icon name="close" size={14} />
          </button>
        </div>
      )}
    </div>
  )
}
