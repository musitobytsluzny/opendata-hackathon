import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import type { Message } from '../chat/assistant'

export type Session = {
  id: string
  messages: Message[]
  activeId: string | null
  createdAt: number
  updatedAt: number
  title?: string
  pinned?: boolean
  draft?: string
}
export const uid = () => crypto.randomUUID()
export const newSession = (messages: Message[] = []): Session => ({
  id: uid(),
  messages,
  activeId: null,
  createdAt: Date.now(),
  updatedAt: Date.now(),
})
export function sessionTitle(session: Session): string {
  if (session.title) return session.title
  const first = session.messages.find((message) => message.role === 'user')
  return first?.role === 'user' ? first.text : session.draft || 'Nová konverzace'
}
function load(key: string): Session[] {
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(key) ?? '[]')
    if (!Array.isArray(parsed)) return []
    return parsed
      .filter(
        (session): session is Session =>
          session &&
          typeof session.id === 'string' &&
          Array.isArray(session.messages) &&
          session.messages.every(
            (message: Message) =>
              message &&
              typeof message.id === 'string' &&
              (message.role === 'assistant'
                ? typeof message.answer?.text === 'string'
                : (message.role === 'user' || message.role === 'error') &&
                  typeof message.text === 'string'),
          ),
      )
      .slice(0, 30)
      .map((session) => ({
        ...session,
        messages: session.messages.slice(-200),
        title: typeof session.title === 'string' ? session.title.slice(0, 100) : undefined,
        draft: typeof session.draft === 'string' ? session.draft.slice(0, 4000) : '',
        updatedAt: Number.isFinite(session.updatedAt) ? session.updatedAt : Date.now(),
      }))
  } catch {
    return []
  }
}
function save(key: string, sessions: Session[], currentId: string) {
  try {
    const stored = sessions
      .filter((session) => session.messages.length || session.draft?.trim())
      .toSorted(
        (a, b) =>
          Number(Boolean(b.pinned)) - Number(Boolean(a.pinned)) || b.updatedAt - a.updatedAt,
      )
      .slice(0, 30)
      .map((session) => ({ ...session, messages: session.messages.slice(-200) }))
    localStorage.setItem(key, JSON.stringify(stored))
    localStorage.setItem(`${key}:active`, currentId)
  } catch {
    /* Storage is optional. */
  }
}
export function useChatSessions(userId?: string, username?: string) {
  const key = `chat_sessions:${userId ?? 'anon'}`
  const [initial] = useState(() => {
    const stored = load(key)
    let hasCurrentStorage = false
    try {
      hasCurrentStorage = localStorage.getItem(key) !== null
    } catch {
      /* Storage optional. */
    }
    const legacy = hasCurrentStorage ? stored : load(`chat_sessions:${username ?? 'anon'}`)
    const sessions = legacy.length ? legacy : [newSession()]
    let id = sessions[0].id
    try {
      const selected = localStorage.getItem(`${key}:active`)
      if (sessions.some((session) => session.id === selected)) id = selected!
    } catch {
      /* Storage is optional. */
    }
    return { sessions, id }
  })
  const [sessions, setSessions] = useState(initial.sessions)
  const [currentId, setCurrentId] = useState(initial.id)
  const sessionsRef = useRef(sessions)
  const currentIdRef = useRef(currentId)
  useLayoutEffect(() => {
    sessionsRef.current = sessions
    currentIdRef.current = currentId
  }, [sessions, currentId])
  useEffect(() => {
    const timer = window.setTimeout(() => save(key, sessions, currentId), 250)
    return () => window.clearTimeout(timer)
  }, [key, sessions, currentId])
  useEffect(() => {
    const persist = () => save(key, sessionsRef.current, currentIdRef.current)
    window.addEventListener('pagehide', persist)
    return () => {
      window.removeEventListener('pagehide', persist)
      persist()
    }
  }, [key])
  const current = sessions.find((session) => session.id === currentId) ?? sessions[0]
  function update(id: string, fn: (session: Session) => Session) {
    setSessions((list) => list.map((session) => (session.id === id ? fn(session) : session)))
  }
  function create(messages: Message[] = []) {
    const session = newSession(messages)
    setSessions((list) => [session, ...list])
    setCurrentId(session.id)
    return session.id
  }
  function remove(id: string) {
    const remaining = sessions.filter((session) => session.id !== id)
    const next = remaining.length ? remaining : [newSession()]
    setSessions(next)
    if (id === currentId) setCurrentId(next[0].id)
  }
  function restore(session: Session) {
    setSessions((list) => [session, ...list.filter((item) => item.id !== session.id)])
    setCurrentId(session.id)
  }
  function clear() {
    const fresh = newSession()
    setSessions([fresh])
    setCurrentId(fresh.id)
    save(key, [fresh], fresh.id)
    try {
      localStorage.removeItem(`chat_sessions:${username ?? 'anon'}`)
    } catch {
      /* Storage optional. */
    }
  }
  return { clear, restore, sessions, current, currentId, setCurrentId, update, create, remove }
}
