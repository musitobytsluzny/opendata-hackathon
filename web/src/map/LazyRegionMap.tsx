import {
  Component,
  Suspense,
  forwardRef,
  lazy,
  memo,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import type { RegionMapHandle, RegionMapProps } from './RegionMap'
import './RegionMap.css'

export type { RegionMapHandle } from './RegionMap'

const Map = lazy(() => import('./RegionMap').then((module) => ({ default: module.RegionMap })))

class MapBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() {
    return { failed: true }
  }
  render() {
    return this.state.failed ? (
      <div className="map-unavailable" role="status">
        Mapu se nepodařilo načíst. Ostatní funkce můžete dál používat.
      </div>
    ) : (
      this.props.children
    )
  }
}

export const RegionMap = memo(
  forwardRef<RegionMapHandle, RegionMapProps>(function DeferredMap(props, ref) {
    const host = useRef<HTMLDivElement>(null)
    const [visible, setVisible] = useState(false)
    useEffect(() => {
      if (!host.current) return
      const observer = new IntersectionObserver((entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setVisible(true)
          observer.disconnect()
        }
      })
      observer.observe(host.current)
      return () => observer.disconnect()
    }, [])
    return (
      <div ref={host} className="region-map">
        {visible && (
          <MapBoundary>
            <Suspense fallback={null}>
              <Map {...props} ref={ref} />
            </Suspense>
          </MapBoundary>
        )}
      </div>
    )
  }),
)
