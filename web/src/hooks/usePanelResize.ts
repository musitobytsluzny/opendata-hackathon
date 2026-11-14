import { useDragResize } from './useDragResize'

export function usePanelResize(width: number, max: number, onChange: (width: number) => void) {
  return useDragResize(width, 330, max, onChange)
}
