import { useEffect, useState } from 'react'
import { usePanelResize } from './usePanelResize'
import { useDragResize } from './useDragResize'

export function useWorkspaceLayout(width: number, onWidthChange: (width: number) => void) {
  const readViewport = () => ({
    width: window.innerWidth,
    height: Math.min(window.innerHeight, window.visualViewport?.height ?? window.innerHeight),
    top: window.visualViewport?.offsetTop ?? 0,
  })
  const [viewport, setViewport] = useState(readViewport)
  const [sheetRatio, setSheetRatio] = useState(0.55)
  useEffect(() => {
    let frame = 0
    const update = () => {
      cancelAnimationFrame(frame)
      frame = requestAnimationFrame(() => setViewport(readViewport()))
    }
    window.addEventListener('resize', update)
    window.visualViewport?.addEventListener('resize', update)
    window.visualViewport?.addEventListener('scroll', update)
    return () => {
      cancelAnimationFrame(frame)
      window.removeEventListener('resize', update)
      window.visualViewport?.removeEventListener('resize', update)
      window.visualViewport?.removeEventListener('scroll', update)
    }
  }, [])
  const mobile = viewport.width <= 720
  const maxWidth = Math.max(330, Math.round(viewport.width * 0.75))
  const panelWidth = Math.min(maxWidth, Math.max(330, width))
  const minHeight = Math.min(240, viewport.height * 0.65)
  const maxHeight = Math.max(minHeight, viewport.height - 176)
  const sheetHeight = Math.max(minHeight, Math.min(maxHeight, viewport.height * sheetRatio))
  const horizontal = usePanelResize(panelWidth, maxWidth, onWidthChange)
  const vertical = useDragResize(
    sheetHeight,
    minHeight,
    maxHeight,
    (height) => setSheetRatio(height / viewport.height),
    'y',
  )
  return {
    viewport,
    mobile,
    maxWidth,
    panelWidth,
    minHeight,
    maxHeight,
    sheetHeight,
    horizontal,
    vertical,
    toggleSheet: () => setSheetRatio(sheetRatio > 0.7 ? 0.4 : 0.85),
  }
}
