import { useEffect, useRef, useState, type KeyboardEvent, type PointerEvent } from 'react'

export function useDragResize(
  value: number,
  min: number,
  max: number,
  onChange: (value: number) => void,
  axis: 'x' | 'y' = 'x',
) {
  const [dragging, setDragging] = useState(false)
  const active = useRef(false)
  const frame = useRef(0)
  const origin = useRef({ position: 0, value })
  const position = (event: PointerEvent<HTMLElement>) =>
    axis === 'x' ? event.clientX : -event.clientY
  const clamp = (next: number) => Math.max(min, Math.min(max, next))
  const finish = () => {
    active.current = false
    setDragging(false)
    cancelAnimationFrame(frame.current)
  }
  useEffect(() => () => cancelAnimationFrame(frame.current), [])
  return {
    dragging,
    handle: {
      onPointerDown(event: PointerEvent<HTMLElement>) {
        if (event.button !== 0) return
        event.preventDefault()
        event.currentTarget.setPointerCapture(event.pointerId)
        origin.current = { position: position(event), value }
        active.current = true
        setDragging(true)
      },
      onPointerMove(event: PointerEvent<HTMLElement>) {
        if (!active.current) return
        const next = clamp(origin.current.value + position(event) - origin.current.position)
        cancelAnimationFrame(frame.current)
        frame.current = requestAnimationFrame(() => onChange(next))
      },
      onPointerUp(event: PointerEvent<HTMLElement>) {
        if (!active.current) return
        onChange(clamp(origin.current.value + position(event) - origin.current.position))
        finish()
        if (event.currentTarget.hasPointerCapture(event.pointerId))
          event.currentTarget.releasePointerCapture(event.pointerId)
      },
      onPointerCancel: finish,
      onLostPointerCapture: finish,
      onKeyDown(event: KeyboardEvent<HTMLElement>) {
        const minus = axis === 'x' ? 'ArrowLeft' : 'ArrowDown'
        const plus = axis === 'x' ? 'ArrowRight' : 'ArrowUp'
        const next =
          event.key === minus
            ? value - (event.shiftKey ? 80 : 20)
            : event.key === plus
              ? value + (event.shiftKey ? 80 : 20)
              : event.key === 'Home'
                ? min
                : event.key === 'End'
                  ? max
                  : null
        if (next === null) return
        event.preventDefault()
        onChange(clamp(next))
      },
    },
  }
}
