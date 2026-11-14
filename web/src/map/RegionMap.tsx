import type { Feature, Position } from 'geojson'
import {
  forwardRef,
  useCallback,
  useLayoutEffect,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from 'react'
import {
  Map as MlMap,
  Marker,
  LngLatBounds,
  type GeoJSONSource,
  type LngLatBoundsLike,
  setWorkerUrl,
  prewarm,
  type ExpressionSpecification,
  type LngLatLike,
  type MapLayerMouseEvent,
  type StyleSpecification,
} from 'maplibre-gl'
import mapWorkerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url'
import 'maplibre-gl/dist/maplibre-gl.css'

import {
  cesko,
  KRAJ_BOUNDS,
  OKRESY,
  OKRES_BOUNDS,
  TOWNS,
  kraj,
  maskGeometry,
  okresy,
  type OkresId,
} from './geo'
import { PALETTES, type PaletteId } from './palette'
import { useSettings } from '../settings/settings'
import './RegionMap.css'

// Vite prebundles the library; its relative default worker URL would point into
// .vite/deps. Resolve a real worker asset and reuse it across route transitions.
setWorkerUrl(mapWorkerUrl)
prewarm()

export type RegionMapHandle = {
  fitKraj: () => void
  focusOkres: (id: OkresId) => void
  zoomIn: () => void
  zoomOut: () => void
}

type Target =
  | { kind: 'kraj' }
  | { kind: 'okres'; id: OkresId }
  | { kind: 'overlay'; bounds: LngLatBoundsLike }
type Camera = { center: LngLatLike; zoom: number; bearing: number; version: number }

const EASE = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2)

type Padding = { top: number; right: number; bottom: number; left: number }

export type RegionMapProps = {
  overlay?: Feature[]
  focusFeatures?: Feature[]
  overlayKey?: string
  onMapClick?: (lon: number, lat: number) => void
  interactive?: boolean
  hoverable?: boolean
  palette?: PaletteId
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
  basemap?: 'satellite' | 'ortho' | 'dark'
  showCadastre?: boolean
  cadastreOpacity?: number
  reducedMotion?: boolean
  onSelect?: (id: OkresId) => void
  className?: string
}

const H: ExpressionSpecification = ['coalesce', ['feature-state', 'h'], 0]
const D: ExpressionSpecification = ['coalesce', ['feature-state', 'd'], 0]
const OKRES_IDS = Object.keys(OKRESY) as OkresId[]

function fillColor(palette: PaletteId): ExpressionSpecification {
  const [low, mid, high] = PALETTES[palette]
  return [
    'interpolate',
    ['linear'],
    ['coalesce', ['feature-state', 'v'], 0],
    0,
    low,
    0.5,
    mid,
    1,
    high,
  ]
}

function fillOpacity(flat: boolean): ExpressionSpecification {
  const [base, lift, dim] = flat ? [0.9, 0.1, -0.3] : [0.44, 0.26, -0.14]
  return [
    'case',
    ['==', ['feature-state', 'v'], null],
    ['*', 0.16, H],
    ['+', base, ['*', lift, H], ['*', dim, D]],
  ]
}

function visibility(on: boolean) {
  return on ? 'visible' : 'none'
}

const ORTOFOTO = 'https://ags.cuzk.cz/arcgis1/rest/services/ORTOFOTO_WM/MapServer/tile/{z}/{y}/{x}'
const CADASTRE =
  'https://ags.cuzk.cz/arcgis/rest/services/RUIAN/MapServer/export?bbox={bbox-epsg-3857}&bboxSR=3857&imageSR=3857&size=256%2C256&format=png32&transparent=true&layers=show%3A5&f=image'

const style: StyleSpecification = {
  version: 8,
  sources: {
    cesko: {
      type: 'geojson',
      data: cesko,
      attribution: 'Hranice ČR © Natural Earth (public domain)',
    },
    s2: {
      type: 'raster',
      tiles: ['https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless_3857/default/g/{z}/{y}/{x}.jpg'],
      tileSize: 256,
      maxzoom: 10,
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
    cadastre: {
      type: 'raster',
      tiles: [CADASTRE],
      tileSize: 256,
      maxzoom: 19,
      bounds: [12.09, 48.55, 18.87, 51.06],
      attribution:
        'Katastrální parcely © <a href="https://ags.cuzk.cz/arcgis/rest/services/RUIAN/MapServer" target="_blank" rel="noreferrer">ČÚZK · RÚIAN</a>',
    },
  },
  layers: [
    { id: 'bg', type: 'background', paint: { 'background-color': '#0d120e' } },
    { id: 'land', type: 'fill', source: 'cesko', paint: { 'fill-color': '#273b2d' } },
    { id: 's2', type: 'raster', source: 's2', paint: { 'raster-fade-duration': 120 } },
    {
      id: 'orto',
      type: 'raster',
      source: 'orto',
      minzoom: 11,
      paint: { 'raster-fade-duration': 120 },
    },
    {
      id: 'cadastre',
      type: 'raster',
      source: 'cadastre',
      minzoom: 13,
      layout: { visibility: 'none' },
      paint: { 'raster-fade-duration': 120, 'raster-opacity': 0.72 },
    },
  ],
}

const DEFAULT_PADDING: Padding = { top: 24, right: 24, bottom: 24, left: 24 }

export const RegionMap = forwardRef<RegionMapHandle, RegionMapProps>(function RegionMap(
  {
    overlay,
    focusFeatures,
    overlayKey,
    onMapClick,
    interactive = true,
    hoverable = false,
    palette,
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
    basemap,
    showCadastre = false,
    cadastreOpacity = 0.72,
    reducedMotion = false,
    onSelect,
    className,
  },
  ref,
) {
  const sharedSettings = useSettings()
  const activeBasemap = basemap ?? sharedSettings.basemap
  const activePalette = palette ?? sharedSettings.palette
  const motionReduced = reducedMotion || sharedSettings.reducedMotion
  const container = useRef<HTMLDivElement>(null)
  const map = useRef<MlMap | null>(null)
  const [ready, setReady] = useState(false)
  const [tileError, setTileError] = useState(false)
  const paddingRef = useRef(padding)
  const onHoverRef = useRef(onHover)
  const valueMarkers = useRef<Marker[]>([])
  const onMapClickRef = useRef(onMapClick)
  const onSelectRef = useRef(onSelect)
  const motionRef = useRef(motionReduced)

  const paletteRef = useRef(activePalette)
  const basemapRef = useRef(activeBasemap)
  useLayoutEffect(() => {
    paletteRef.current = activePalette
    basemapRef.current = activeBasemap
  }, [activePalette, activeBasemap])
  const glowRef = useRef<{ d: number; h: Partial<Record<OkresId, number>> }>({ d: 0, h: {} })
  const maskRef = useRef(maskOpacity)
  const labelRef = useRef(label)
  useLayoutEffect(() => {
    paddingRef.current = padding
    maskRef.current = maskOpacity
    onHoverRef.current = onHover
    labelRef.current = label
    onMapClickRef.current = onMapClick
    onSelectRef.current = onSelect
    motionRef.current = motionReduced
  }, [padding, maskOpacity, onHover, label, onSelect, onMapClick, motionReduced])

  const target = useRef<Target>({ kind: 'kraj' })
  const targetVersion = useRef(0)
  const cameras = useRef<Record<string, Camera>>({})
  const viewKeyRef = useRef(viewKey)

  const frame = useCallback((duration: number) => {
    const m = map.current
    if (!m) return
    const t = target.current
    const bounds =
      t.kind === 'overlay' ? t.bounds : t.kind === 'okres' ? OKRES_BOUNDS[t.id] : KRAJ_BOUNDS
    m.fitBounds(bounds, {
      padding: paddingRef.current,
      ...(t.kind === 'okres' ? { maxZoom: 11.5 } : t.kind === 'overlay' ? { maxZoom: 17 } : {}),
      duration:
        motionRef.current || window.matchMedia('(prefers-reduced-motion: reduce)').matches
          ? 0
          : duration,
      bearing: 0,
      pitch: 0,
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
      interactive: interactive || hoverable,
      ...(interactive
        ? {}
        : {
            dragPan: false,
            scrollZoom: false,
            boxZoom: false,
            doubleClickZoom: false,
            keyboard: false,
            touchZoomRotate: false,
            touchPitch: false,
          }),
      attributionControl: { compact: false },
      maxBounds: [
        [-2, 42],
        [28, 58],
      ],
      minZoom: 6,
      maxZoom: 19,
      dragRotate: false,
      pitchWithRotate: false,
      fadeDuration: 0,
      pixelRatio: Math.min(window.devicePixelRatio || 1, interactive ? 2 : 1.25),
      renderWorldCopies: false,
      refreshExpiredTiles: false,
    })
    map.current = m
    let resizeFrame = 0
    const resizeObserver = new ResizeObserver(() => {
      cancelAnimationFrame(resizeFrame)
      resizeFrame = requestAnimationFrame(() => m.resize())
    })
    resizeObserver.observe(container.current)
    m.touchZoomRotate?.disableRotation()
    m.getCanvas().setAttribute('aria-label', labelRef.current)
    m.getCanvas().setAttribute('role', 'img')
    if (!interactive) m.getCanvas().setAttribute('tabindex', '-1')

    m.on('error', (event) => {
      const sourceId = (event as unknown as { sourceId?: string }).sourceId
      if (sourceId === 's2' || sourceId === 'orto' || sourceId === 'cadastre') setTileError(true)
    })
    m.on('sourcedata', (event) => {
      if (
        (event.sourceId === 's2' || event.sourceId === 'orto' || event.sourceId === 'cadastre') &&
        event.isSourceLoaded
      )
        setTileError(false)
    })

    // Geometry must not wait for remote raster tiles.
    m.once('style.load', () => {
      m.getCanvasContainer().classList.add('is-ready')
      m.addSource('okresy', { type: 'geojson', data: okresy, promoteId: 'id' })
      m.addSource('mask', {
        type: 'geojson',
        data: { type: 'Feature', properties: {}, geometry: maskGeometry() },
      })
      m.addSource('kraj', { type: 'geojson', data: kraj })

      m.addLayer({
        id: 'flat',
        type: 'fill',
        source: 'kraj',
        paint: { 'fill-color': '#242c26' },
        layout: { visibility: visibility(basemapRef.current === 'dark') },
      })
      m.addLayer({
        id: 'okresy-fill',
        type: 'fill',
        source: 'okresy',
        paint: {
          'fill-color': fillColor(paletteRef.current),
          'fill-opacity': fillOpacity(basemapRef.current === 'dark'),
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
            ['boolean', ['feature-state', 'focused'], false],
            1,
            ['+', 0.5, ['*', 0.5, H]],
          ],
          'line-width': [
            'case',
            ['boolean', ['feature-state', 'focused'], false],
            3.5,
            ['+', 1, ['*', 1.5, H]],
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

      if (interactive || hoverable) {
        m.on('mousemove', 'okresy-fill', (e: MapLayerMouseEvent) => {
          const id = e.features?.[0]?.properties?.id as OkresId | undefined
          if (interactive) m.getCanvas().style.cursor = id ? 'pointer' : ''
          onHoverRef.current?.(id ?? null)
        })
        m.on('click', 'okresy-fill', (e: MapLayerMouseEvent) => {
          const id = e.features?.[0]?.properties?.id as OkresId | undefined
          if (interactive && !onMapClickRef.current && id && OKRESY[id]) onSelectRef.current?.(id)
        })
        m.on('mouseleave', 'okresy-fill', () => {
          m.getCanvas().style.cursor = ''
          onHoverRef.current?.(null)
        })
      }

      m.addSource('workspace', {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
      })
      const color: ExpressionSpecification = ['coalesce', ['get', '_color'], '#c3d6ad']
      m.addLayer({
        id: 'workspace-fill',
        type: 'fill',
        source: 'workspace',
        filter: ['==', ['geometry-type'], 'Polygon'],
        paint: { 'fill-color': color, 'fill-opacity': 0.25 },
      })
      m.addLayer({
        id: 'workspace-line',
        type: 'line',
        source: 'workspace',
        filter: ['!=', ['geometry-type'], 'Point'],
        paint: { 'line-color': color, 'line-width': 3 },
      })
      m.addLayer({
        id: 'workspace-point',
        type: 'circle',
        source: 'workspace',
        filter: ['==', ['geometry-type'], 'Point'],
        paint: {
          'circle-color': color,
          'circle-radius': 7,
          'circle-stroke-color': '#172019',
          'circle-stroke-width': 2,
        },
      })
      m.on('click', (event) => onMapClickRef.current?.(event.lngLat.lng, event.lngLat.lat))
      setReady(true)
    })

    return () => {
      setReady(false)
      resizeObserver.disconnect()
      cancelAnimationFrame(resizeFrame)
      m.remove()
      map.current = null
    }
  }, [interactive, hoverable])

  useEffect(() => {
    const m = map.current
    if (!m || !ready) return
    ;(m.getSource('workspace') as GeoJSONSource).setData({
      type: 'FeatureCollection',
      features: overlay ?? [],
    })
    const markers: Marker[] = []
    for (const feature of overlay ?? []) {
      if (markers.length >= 25 || !feature.geometry) break
      const geometry = feature.geometry
      let coordinates: Position | undefined
      if (geometry.type === 'Point') coordinates = geometry.coordinates
      else if (geometry.type === 'LineString' && feature.properties?.measurement)
        coordinates = geometry.coordinates[Math.floor(geometry.coordinates.length / 2)]
      if (!coordinates || !feature.properties?.label) continue
      const element = document.createElement('span')
      element.className = 'workspace-map-label'
      element.textContent = String(feature.properties.label)
      markers.push(
        new Marker({ element, anchor: 'bottom', offset: [0, -10] })
          .setLngLat([coordinates[0], coordinates[1]])
          .addTo(m),
      )
    }
    return () => markers.forEach((marker) => marker.remove())
  }, [overlay, ready])

  useEffect(() => {
    if (!ready || !overlayKey || !overlay?.length) return
    const bounds = new LngLatBounds()
    function extend(coordinates: unknown) {
      if (!Array.isArray(coordinates)) return
      if (typeof coordinates[0] === 'number' && typeof coordinates[1] === 'number') {
        if (Number.isFinite(coordinates[0]) && Number.isFinite(coordinates[1]))
          bounds.extend([coordinates[0], coordinates[1]])
      } else coordinates.forEach(extend)
    }
    for (const feature of focusFeatures ?? overlay)
      if (feature.geometry && 'coordinates' in feature.geometry)
        extend(feature.geometry.coordinates)
    if (!bounds.isEmpty()) setTarget({ kind: 'overlay', bounds: bounds.toArray() })
    // Geometry visibility changes update the source; camera moves only for an explicit target key.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [overlayKey, ready])

  useEffect(() => {
    const m = map.current
    if (!m || !ready) return
    m.setPaintProperty('mask', 'fill-opacity', maskOpacity)
  }, [maskOpacity, ready])

  useEffect(() => {
    map.current?.getCanvas().setAttribute('aria-label', label)
  }, [label])

  useEffect(() => {
    if (!showTowns) return
    const m = map.current
    if (!m) return
    const markers = TOWNS.map((t) => {
      const el = document.createElement('div')
      el.className = ['town', t.major ? 'town--major' : '', t.left ? 'town--left' : '']
        .filter(Boolean)
        .join(' ')
      el.setAttribute('aria-hidden', 'true')
      el.innerHTML = '<span class="town__dot"></span><span class="town__name"></span>'
      el.querySelector('.town__name')!.textContent = t.name
      return new Marker({ element: el, anchor: t.left ? 'right' : 'left' }).setLngLat(t.at).addTo(m)
    })
    return () => markers.forEach((mk) => mk.remove())
  }, [showTowns, interactive, hoverable])

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
          const name = document.createElement('span')
          name.className = 'value-pill__name'
          const nameText = document.createElement('span')
          nameText.textContent = OKRESY[id].name
          name.appendChild(nameText)
          pill.append(name, text)
          el.appendChild(pill)
          valueMarkers.current.push(
            new Marker({ element: el }).setLngLat(OKRESY[id].center).addTo(m),
          )
        }
      }
    }
    if (ready) apply()
  }, [values, labels, ready])

  useEffect(() => {
    const m = map.current
    if (!m || !ready) return
    valueMarkers.current.forEach((mk) => {
      const el = mk.getElement()
      el.classList.toggle('is-hovered', el.dataset.okres === hovered)
      el.classList.toggle('is-focused', el.dataset.okres === focused)
    })
  }, [hovered, focused, values, ready])

  useEffect(() => {
    const m = map.current
    if (!m || !ready) return
    const instant = motionReduced || window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const glow = glowRef.current
    let raf = 0
    let last = 0
    const tick = (t: number) => {
      const dt = last ? Math.min(t - last, 64) : 16
      last = t
      let moving = false
      const step = (from: number, to: number) => {
        if (instant) return to
        const next = from + (to - from) * (1 - Math.exp(-dt / (to > from ? 80 : 150)))
        if (Math.abs(to - next) < 0.004) return to
        moving = true
        return next
      }
      glow.d = step(glow.d, hovered ? 1 : 0)
      for (const id of OKRES_IDS) {
        const h = step(glow.h[id] ?? 0, id === hovered ? 1 : 0)
        glow.h[id] = h
        m.setFeatureState({ source: 'okresy', id }, { h, d: glow.d * (1 - h) })
      }
      if (moving) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [hovered, ready, motionReduced])

  useEffect(() => {
    const apply = () => {
      const m = map.current
      if (!m) return
      for (const id of Object.keys(OKRESY) as OkresId[]) {
        m.setFeatureState({ source: 'okresy', id }, { focused: id === focused })
      }
    }
    if (ready) apply()
  }, [focused, values, ready])

  useEffect(() => {
    const m = map.current
    if (!m || !ready) return
    m.setLayerZoomRange('orto', activeBasemap === 'ortho' ? 6 : 11, 24)
    const flat = activeBasemap === 'dark'
    m.setLayoutProperty('flat', 'visibility', visibility(flat))
    for (const id of ['s2', 'orto', 'land'])
      m.setLayoutProperty(id, 'visibility', visibility(!flat))
    m.setLayoutProperty('cadastre', 'visibility', visibility(showCadastre))
    m.setPaintProperty('cadastre', 'raster-opacity', cadastreOpacity)
    m.setPaintProperty('okresy-fill', 'fill-opacity', fillOpacity(flat))
    m.setPaintProperty('okresy-fill', 'fill-color', fillColor(activePalette))
    // Reuse coarse satellite tiles outside Czech ortho coverage.
    m.setLayerZoomRange('s2', 0, 24)
  }, [activeBasemap, activePalette, cadastreOpacity, ready, showCadastre])

  useEffect(() => {
    const m = map.current
    if (!m || !ready) {
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
    frame(drift ? 0 : 640)
  }, [viewKey, padding.top, padding.right, padding.bottom, padding.left, frame, ready, drift])

  useEffect(() => {
    const m = map.current
    if (!m || !drift || !ready || motionReduced) return
    const media = window.matchMedia('(prefers-reduced-motion: reduce)')
    let baseCenter = m.getCenter()
    let baseBearing = m.getBearing()
    let basePitch = m.getPitch()
    let baseZoom = m.getZoom()
    const poses = [
      { bearing: -1.5, zoom: 0.04 },
      { bearing: 1.5, zoom: -0.04 },
      { bearing: 0.5, zoom: 0.025 },
      { bearing: -0.5, zoom: -0.025 },
    ]
    let step = 0
    let disposed = false
    let timer = 0
    let ownsAnimation = false

    const play = () => {
      if (disposed || document.hidden || media.matches || m.isMoving()) return
      const pose = poses[step % poses.length]
      const duration = step === 0 ? 9000 : 16000
      step += 1
      ownsAnimation = true
      m.easeTo({
        bearing: baseBearing + pose.bearing,
        pitch: basePitch,
        zoom: Math.max(m.getMinZoom(), baseZoom + pose.zoom),
        around: baseCenter,
        duration,
        easing: (t) => (1 - Math.cos(Math.PI * t)) / 2,
      })
    }
    const schedule = () => {
      if (ownsAnimation) {
        ownsAnimation = false
      } else {
        baseCenter = m.getCenter()
        baseBearing = m.getBearing()
        basePitch = m.getPitch()
        baseZoom = m.getZoom()
      }
      if (disposed || document.hidden || media.matches) return
      window.clearTimeout(timer)
      timer = window.setTimeout(play, 350)
    }
    const onVisibility = () => {
      window.clearTimeout(timer)
      if (document.hidden || media.matches) {
        if (ownsAnimation) {
          m.stop()
          ownsAnimation = false
          baseCenter = m.getCenter()
          baseBearing = m.getBearing()
          basePitch = m.getPitch()
          baseZoom = m.getZoom()
        }
      } else schedule()
    }
    m.on('moveend', schedule)
    document.addEventListener('visibilitychange', onVisibility)
    media.addEventListener('change', onVisibility)
    schedule()
    return () => {
      disposed = true
      window.clearTimeout(timer)
      m.off('moveend', schedule)
      document.removeEventListener('visibilitychange', onVisibility)
      media.removeEventListener('change', onVisibility)
      if (ownsAnimation && map.current === m) m.stop()
    }
  }, [
    drift,
    interactive,
    ready,
    motionReduced,
    padding.top,
    padding.right,
    padding.bottom,
    padding.left,
  ])

  const classes = [
    'region-map',
    labels ? 'region-map--values' : '',
    hoverable && !interactive ? 'region-map--hover' : '',
    className ?? '',
  ]
    .filter(Boolean)
    .join(' ')
  return (
    <>
      <div ref={container} className={classes} role="region" aria-label={label} />
      {tileError && interactive && (
        <p className="map-tile-status" role="status">
          Mapové dlaždice se načítají pomalu. Hranice, výsledky a výběr parcel zůstávají dostupné.
        </p>
      )}
    </>
  )
})
