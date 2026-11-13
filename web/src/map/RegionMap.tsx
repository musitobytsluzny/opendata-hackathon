import {
  forwardRef,
  useCallback,
  useLayoutEffect,
  useEffect,
  useImperativeHandle,
  useRef,
} from 'react'
import {
  Map as MlMap,
  Marker,
  setWorkerUrl,
  type LngLatLike,
  type MapLayerMouseEvent,
  type StyleSpecification,
} from 'maplibre-gl'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'
import 'maplibre-gl/dist/maplibre-gl.css'

setWorkerUrl(workerUrl)
import {
  KRAJ_BOUNDS,
  OKRESY,
  OKRES_BOUNDS,
  TOWNS,
  kraj,
  maskGeometry,
  okresy,
  type OkresId,
} from './geo'
import './RegionMap.css'

export type RegionMapHandle = {
  fitKraj: () => void
  focusOkres: (id: OkresId) => void
  zoomIn: () => void
  zoomOut: () => void
}

type Target = { kind: 'kraj' } | { kind: 'okres'; id: OkresId }
type Camera = { center: LngLatLike; zoom: number; bearing: number; version: number }

const EASE = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2)

type Padding = { top: number; right: number; bottom: number; left: number }

export type RegionMapProps = {
  interactive?: boolean
  maskOpacity?: number
  padding?: Padding
  values?: Partial<Record<OkresId, number>> | null
  labels?: Partial<Record<OkresId, string>> | null
  hovered?: OkresId | null
  onHover?: (id: OkresId | null) => void
  drift?: boolean
  showTowns?: boolean
  focused?: OkresId | null
  viewKey?: string
  label?: string
  className?: string
}

const ORTOFOTO = 'https://ags.cuzk.cz/arcgis1/rest/services/ORTOFOTO_WM/MapServer/tile/{z}/{y}/{x}'

const style: StyleSpecification = {
  version: 8,
  sources: {
    s2: {
      type: 'raster',
      tiles: ['https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless_3857/default/g/{z}/{y}/{x}.jpg'],
      tileSize: 256,
      maxzoom: 14,
      attribution:
        '<a href="https://s2maps.eu" target="_blank" rel="noreferrer">Sentinel-2 cloudless</a> © EOX, Copernicus 2016',
    },
    orto: {
      type: 'raster',
      tiles: [ORTOFOTO],
      tileSize: 256,
      maxzoom: 19,
      bounds: [12.09, 48.55, 18.87, 51.06],
      attribution:
        'Ortofoto © <a href="https://cuzk.gov.cz" target="_blank" rel="noreferrer">ČÚZK</a>',
    },
  },
  layers: [
    { id: 'bg', type: 'background', paint: { 'background-color': '#0d120e' } },
    { id: 's2', type: 'raster', source: 's2', paint: { 'raster-fade-duration': 240 } },
    { id: 'orto', type: 'raster', source: 'orto', paint: { 'raster-fade-duration': 240 } },
  ],
}

const DEFAULT_PADDING: Padding = { top: 24, right: 24, bottom: 24, left: 24 }

export const RegionMap = forwardRef<RegionMapHandle, RegionMapProps>(function RegionMap(
  {
    interactive = true,
    maskOpacity = 0.68,
    padding = DEFAULT_PADDING,
    values = null,
    labels = null,
    hovered = null,
    onHover,
    drift = false,
    showTowns = true,
    focused = null,
    viewKey = 'default',
    label = 'Mapa Plzeňského kraje',
    className,
  },
  ref,
) {
  const container = useRef<HTMLDivElement>(null)
  const map = useRef<MlMap | null>(null)
  const ready = useRef(false)
  const paddingRef = useRef(padding)
  const onHoverRef = useRef(onHover)
  const valueMarkers = useRef<Marker[]>([])
  const pending = useRef<() => void>(() => {})

  const maskRef = useRef(maskOpacity)
  const labelRef = useRef(label)
  useLayoutEffect(() => {
    paddingRef.current = padding
    maskRef.current = maskOpacity
    onHoverRef.current = onHover
    labelRef.current = label
  }, [padding, maskOpacity, onHover, label])

  const target = useRef<Target>({ kind: 'kraj' })
  const targetVersion = useRef(0)
  const cameras = useRef<Record<string, Camera>>({})
  const viewKeyRef = useRef(viewKey)

  const frame = useCallback((duration: number) => {
    const m = map.current
    if (!m) return
    const t = target.current
    const bounds = t.kind === 'okres' ? OKRES_BOUNDS[t.id] : KRAJ_BOUNDS
    m.fitBounds(bounds, {
      padding: paddingRef.current,
      ...(t.kind === 'okres' ? { maxZoom: 11.5 } : {}),
      duration,
      easing: EASE,
    })
  }, [])

  function setTarget(t: Target) {
    target.current = t
    targetVersion.current += 1
    frame(800)
  }

  useImperativeHandle(ref, () => ({
    fitKraj: () => setTarget({ kind: 'kraj' }),
    focusOkres: (id: OkresId) => setTarget({ kind: 'okres', id }),
    zoomIn: () => map.current?.zoomIn({ duration: 300 }),
    zoomOut: () => map.current?.zoomOut({ duration: 300 }),
  }))

  useEffect(() => {
    if (!container.current) return
    const m = new MlMap({
      container: container.current,
      style,
      bounds: KRAJ_BOUNDS,
      fitBoundsOptions: { padding: paddingRef.current },
      interactive,
      attributionControl: { compact: false },
      maxBounds: [
        [-2, 42],
        [28, 58],
      ],
      minZoom: 6,
      maxZoom: 17,
      dragRotate: false,
      pitchWithRotate: false,
      fadeDuration: 0,
    })
    map.current = m
    m.touchZoomRotate?.disableRotation()
    m.getCanvas().setAttribute('aria-label', labelRef.current)
    m.getCanvas().setAttribute('role', 'img')
    if (!interactive) m.getCanvas().setAttribute('tabindex', '-1')

    m.on('load', () => {
      m.addSource('okresy', { type: 'geojson', data: okresy, promoteId: 'id' })
      m.addSource('mask', {
        type: 'geojson',
        data: { type: 'Feature', properties: {}, geometry: maskGeometry() },
      })
      m.addSource('kraj', { type: 'geojson', data: kraj })

      m.addLayer({
        id: 'okresy-fill',
        type: 'fill',
        source: 'okresy',
        paint: {
          'fill-color': [
            'interpolate',
            ['linear'],
            ['coalesce', ['feature-state', 'v'], 0],
            0,
            '#dce8f6',
            0.5,
            '#5b93d3',
            1,
            '#1b4c85',
          ],
          'fill-opacity': [
            'case',
            ['==', ['feature-state', 'v'], null],
            ['case', ['boolean', ['feature-state', 'hover'], false], 0.14, 0],
            ['case', ['boolean', ['feature-state', 'hover'], false], 0.68, 0.44],
          ],
          'fill-opacity-transition': { duration: 500 },
        },
      })
      m.addLayer({
        id: 'okresy-line',
        type: 'line',
        source: 'okresy',
        paint: {
          'line-color': '#ffffff',
          'line-opacity': [
            'case',
            [
              'any',
              ['boolean', ['feature-state', 'hover'], false],
              ['boolean', ['feature-state', 'focused'], false],
            ],
            1,
            0.5,
          ],
          'line-width': [
            'case',
            ['boolean', ['feature-state', 'focused'], false],
            3.5,
            ['boolean', ['feature-state', 'hover'], false],
            2.5,
            1,
          ],
        },
      })
      m.addLayer({
        id: 'mask',
        type: 'fill',
        source: 'mask',
        paint: {
          'fill-color': '#0b100c',
          'fill-opacity': maskRef.current,
          'fill-opacity-transition': { duration: 400 },
        },
      })
      m.addLayer({
        id: 'kraj-glow',
        type: 'line',
        source: 'kraj',
        paint: { 'line-color': '#000000', 'line-width': 8, 'line-opacity': 0.25, 'line-blur': 6 },
      })
      m.addLayer({
        id: 'kraj-line',
        type: 'line',
        source: 'kraj',
        paint: { 'line-color': '#ffffff', 'line-width': 2.5 },
        layout: { 'line-join': 'round' },
      })

      if (interactive) {
        m.on('mousemove', 'okresy-fill', (e: MapLayerMouseEvent) => {
          const id = e.features?.[0]?.properties?.id as OkresId | undefined
          m.getCanvas().style.cursor = id ? 'pointer' : ''
          onHoverRef.current?.(id ?? null)
        })
        m.on('mouseleave', 'okresy-fill', () => {
          m.getCanvas().style.cursor = ''
          onHoverRef.current?.(null)
        })
      }

      ready.current = true
      pending.current()
    })

    return () => {
      ready.current = false
      m.remove()
      map.current = null
    }
  }, [interactive])

  useEffect(() => {
    const m = map.current
    if (!m || !ready.current) return
    m.setPaintProperty('mask', 'fill-opacity', maskOpacity)
  }, [maskOpacity])

  useEffect(() => {
    map.current?.getCanvas().setAttribute('aria-label', label)
  }, [label])

  useEffect(() => {
    if (!showTowns) return
    const m = map.current
    if (!m) return
    const markers = TOWNS.map((t) => {
      const el = document.createElement('div')
      el.className = t.major ? 'town town--major' : 'town'
      el.setAttribute('aria-hidden', 'true')
      el.innerHTML = '<span class="town__dot"></span><span class="town__name"></span>'
      el.querySelector('.town__name')!.textContent = t.name
      return new Marker({ element: el, anchor: 'left' }).setLngLat(t.at).addTo(m)
    })
    return () => markers.forEach((mk) => mk.remove())
  }, [showTowns, interactive])

  useEffect(() => {
    const apply = () => {
      const m = map.current
      if (!m) return
      for (const id of Object.keys(OKRESY) as OkresId[]) {
        const v = values?.[id]
        m.setFeatureState({ source: 'okresy', id }, { v: v ?? null })
      }
      valueMarkers.current.forEach((mk) => mk.remove())
      valueMarkers.current = []
      if (labels) {
        for (const [id, text] of Object.entries(labels) as [OkresId, string][]) {
          const el = document.createElement('div')
          el.className = 'value-marker'
          el.dataset.okres = id
          el.setAttribute('aria-hidden', 'true')
          const pill = document.createElement('span')
          pill.className = 'value-pill tabular'
          pill.textContent = text
          el.appendChild(pill)
          valueMarkers.current.push(
            new Marker({ element: el }).setLngLat(OKRESY[id].center).addTo(m),
          )
        }
      }
    }
    if (ready.current) apply()
    else pending.current = apply
  }, [values, labels])

  useEffect(() => {
    const m = map.current
    if (!m || !ready.current) return
    for (const id of Object.keys(OKRESY) as OkresId[]) {
      m.setFeatureState({ source: 'okresy', id }, { hover: id === hovered })
    }
    valueMarkers.current.forEach((mk) => {
      const el = mk.getElement()
      el.classList.toggle('is-hovered', el.dataset.okres === hovered)
      el.classList.toggle('is-focused', el.dataset.okres === focused)
    })
  }, [hovered, focused, values])

  useEffect(() => {
    const apply = () => {
      const m = map.current
      if (!m) return
      for (const id of Object.keys(OKRESY) as OkresId[]) {
        m.setFeatureState({ source: 'okresy', id }, { focused: id === focused })
      }
    }
    if (ready.current) apply()
  }, [focused, values])

  useEffect(() => {
    const m = map.current
    if (!m || !drift) return
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    let raf = 0
    let last = performance.now()
    const tick = (t: number) => {
      const dt = t - last
      if (document.hidden) {
        last = t
      } else if (dt >= 1000 / 30) {
        last = t
        m.setBearing(m.getBearing() + Math.min(dt, 100) * 0.0016)
      }
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [drift, interactive])

  useEffect(() => {
    const m = map.current
    if (!m || !ready.current) {
      viewKeyRef.current = viewKey
      return
    }
    const prev = viewKeyRef.current
    if (prev !== viewKey) {
      const c = m.getCenter()
      cameras.current[prev] = {
        center: [c.lng, c.lat],
        zoom: m.getZoom(),
        bearing: m.getBearing(),
        version: targetVersion.current,
      }
      viewKeyRef.current = viewKey
      const saved = cameras.current[viewKey]
      if (saved && saved.version === targetVersion.current) {
        m.easeTo({
          center: saved.center,
          zoom: saved.zoom,
          bearing: saved.bearing,
          duration: 640,
          easing: EASE,
        })
        return
      }
    }
    frame(640)
  }, [viewKey, padding.top, padding.right, padding.bottom, padding.left, frame])

  const classes = ['region-map', labels ? 'region-map--values' : '', className ?? '']
    .filter(Boolean)
    .join(' ')
  return <div ref={container} className={classes} role="region" aria-label={label} />
})
