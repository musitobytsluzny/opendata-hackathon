import { useDeferredValue, useMemo, useState } from 'react'
import { Icon } from '../components/Icon'
import { sessionTitle, type Session } from '../hooks/useChatSessions'

type Props = {
  sessions: Session[]
  currentId: string
  loadingIn: string | null
  onOpen: (id: string) => void
  onDelete: (id: string) => void
  onRename: (id: string, title: string) => void
  onPin: (id: string) => void
  onExport: () => void
}
const searchable = (text: string) =>
  text
    .normalize('NFD')
    .replace(/\p{Diacritic}/gu, '')
    .toLocaleLowerCase('cs')
const dateFormat = new Intl.DateTimeFormat('cs', { day: 'numeric', month: 'short' })

export function HistoryPanel({
  sessions,
  currentId,
  loadingIn,
  onOpen,
  onDelete,
  onRename,
  onPin,
  onExport,
}: Props) {
  const [search, setSearch] = useState('')
  const query = useDeferredValue(searchable(search.trim()))
  const [renaming, setRenaming] = useState<string | null>(null)
  const [title, setTitle] = useState('')
  const history = useMemo(
    () =>
      sessions
        .filter((session) => session.messages.length || session.draft?.trim())
        .filter(
          (session) =>
            !query ||
            searchable(
              [
                sessionTitle(session),
                ...session.messages.map((message) =>
                  message.role === 'assistant' ? message.answer.text : message.text,
                ),
              ].join(' '),
            ).includes(query),
        )
        .toSorted(
          (a, b) =>
            Number(Boolean(b.pinned)) - Number(Boolean(a.pinned)) || b.updatedAt - a.updatedAt,
        ),
    [sessions, query],
  )
  return (
    <div
      id="popover-history"
      className="popover history-panel"
      role="dialog"
      aria-label="Historie konverzací"
    >
      <div className="popover__heading">
        Vaše konverzace <span>{history.length}</span>
      </div>
      <label className="history-search">
        <Icon name="search" size={16} />
        <input
          aria-label="Hledat v konverzacích"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Hledat v názvech i zprávách…"
        />
      </label>
      <ul className="sessions" aria-label="Uložené konverzace">
        {history.map((session) => (
          <li
            key={session.id}
            className={`session${session.id === currentId ? ' is-current' : ''}`}
          >
            {renaming === session.id ? (
              <form
                className="session__rename"
                onSubmit={(event) => {
                  event.preventDefault()
                  if (title.trim()) {
                    onRename(session.id, title.trim())
                    setRenaming(null)
                  }
                }}
              >
                <input
                  aria-label="Název konverzace"
                  value={title}
                  maxLength={100}
                  onChange={(event) => setTitle(event.target.value)}
                />
                <button type="submit" className="icon-btn" aria-label="Uložit název">
                  <Icon name="check" size={16} />
                </button>
                <button
                  type="button"
                  className="icon-btn"
                  aria-label="Zrušit přejmenování"
                  onClick={() => setRenaming(null)}
                >
                  <Icon name="close" size={16} />
                </button>
              </form>
            ) : (
              <>
                <button
                  type="button"
                  className="session__open"
                  aria-current={session.id === currentId ? 'true' : undefined}
                  onClick={() => onOpen(session.id)}
                >
                  <span className="session__title">
                    {session.pinned && <Icon name="pin" size={12} />}
                    {sessionTitle(session)}
                  </span>
                  <span className="session__meta">
                    {dateFormat.format(session.updatedAt)} ·{' '}
                    {session.messages.filter((message) => message.role === 'user').length} dotazů
                    {session.id === loadingIn ? ' · odpovídám…' : ''}
                    {session.draft ? ' · rozepsáno' : ''}
                  </span>
                </button>
                <div className="session__actions">
                  <button
                    type="button"
                    className="icon-btn"
                    aria-label={`${session.pinned ? 'Odepnout' : 'Připnout'} konverzaci: ${sessionTitle(session)}`}
                    aria-pressed={Boolean(session.pinned)}
                    onClick={() => onPin(session.id)}
                  >
                    <Icon name="pin" size={14} />
                  </button>
                  <button
                    type="button"
                    className="icon-btn"
                    aria-label={`Přejmenovat konverzaci: ${sessionTitle(session)}`}
                    onClick={() => {
                      setRenaming(session.id)
                      setTitle(sessionTitle(session).slice(0, 100))
                    }}
                  >
                    <Icon name="edit" size={14} />
                  </button>
                  <button
                    type="button"
                    className="icon-btn"
                    aria-label={`Smazat konverzaci: ${sessionTitle(session)}`}
                    onClick={() => onDelete(session.id)}
                  >
                    <Icon name="trash" size={14} />
                  </button>
                </div>
              </>
            )}
          </li>
        ))}
      </ul>
      {!history.length && (
        <p className="popover__empty">
          {query
            ? 'Této frázi neodpovídá žádná konverzace.'
            : 'První konverzace se tu uloží automaticky.'}
        </p>
      )}
      <div className="popover__rule" />
      <button
        type="button"
        className="popover__item"
        disabled={!sessions.find((session) => session.id === currentId)?.messages.length}
        onClick={onExport}
      >
        <Icon name="download" size={16} />
        Stáhnout aktuální konverzaci (.md)
      </button>
      <p className="history-note">Historie a rozepsané dotazy se ukládají v tomto prohlížeči.</p>
    </div>
  )
}
