import type { ReactNode } from 'react'
import { createPortal } from 'react-dom'

// Keep dialogs outside the resizable panel's containing block, especially on mobile.
export function PopoverPortal({ children }: { children: ReactNode }) {
  return createPortal(children, document.querySelector('.app') ?? document.body)
}
