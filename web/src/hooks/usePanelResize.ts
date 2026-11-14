import { useEffect, useRef, useState, type KeyboardEvent, type PointerEvent } from 'react'

export function usePanelResize(width: number, max: number, onChange: (width: number) => void) {
  const [dragging, setDragging] = useState(false)
  const frame = useRef(0)
  const origin = useRef({ x: 0, width })
  const clamp = (value: number) => Math.max(330, Math.min(max, value))
  useEffect(() => () => cancelAnimationFrame(frame.current), [])
  function onPointerDown(event: PointerEvent<HTMLElement>) {
    if (event.button !== 0) return
    event.preventDefault()
    event.currentTarget.setPointerCapture(event.pointerId)
    origin.current = { x: event.clientX, width }
    setDragging(true)
  }
  function onPointerMove(event: PointerEvent<HTMLElement>) {
    if (!dragging) return
    const next = clamp(origin.current.width + event.clientX - origin.current.x)
    cancelAnimationFrame(frame.current)
    frame.current = requestAnimationFrame(() => onChange(next))
  }
  function onPointerUp(event: PointerEvent<HTMLElement>) {
    if (!dragging) return
    cancelAnimationFrame(frame.current)
    onChange(clamp(origin.current.width + event.clientX - origin.current.x))
    if (event.currentTarget.hasPointerCapture(event.pointerId))
      event.currentTarget.releasePointerCapture(event.pointerId)
    setDragging(false)
  }
  function onKeyDown(event: KeyboardEvent<HTMLElement>) {
    const next =
      event.key === 'ArrowLeft'
        ? width - (event.shiftKey ? 80 : 20)
        : event.key === 'ArrowRight'
          ? width + (event.shiftKey ? 80 : 20)
          : event.key === 'Home'
            ? 330
            : event.key === 'End'
              ? max
              : null
    if (next === null) return
    event.preventDefault()
    onChange(clamp(next))
  }
  return {
    dragging,
    handle: {
      onPointerDown,
      onPointerMove,
      onPointerUp,
      onPointerCancel: () => setDragging(false),
      onLostPointerCapture: () => setDragging(false),
      onKeyDown,
    },
  }
}
