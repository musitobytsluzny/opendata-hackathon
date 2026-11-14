import { useMemo, useState } from 'react'
import type { Artifact, Message } from '../chat/assistant'

const COLORS = ['#c3d6ad', '#e2bb87', '#92c3d7', '#d5a8c4', '#b8b5df', '#c7cc80']
export function useMapLayers(messages: Message[], sessionId: string) {
  const base = useMemo(() => {
    const layers = new Map<string, { artifact: Artifact; visible: boolean; action: string }>()
    for (const message of messages) {
      if (message.role !== 'assistant') continue
      if (message.answer.artifacts?.some((artifact) => artifact.view === 'map')) layers.clear()
      for (const artifact of message.answer.artifacts ?? [])
        if (artifact.view === 'map')
          layers.set(artifact.result_id, { artifact, visible: true, action: message.id })
      for (const action of message.answer.layer_actions ?? []) {
        const layer = layers.get(action.result_id)
        if (layer)
          layers.set(action.result_id, { ...layer, visible: action.visible, action: message.id })
      }
    }
    return [...layers.values()].slice(-12)
  }, [messages])
  const [manual, setManual] = useState<{
    session: string
    baseAction?: string
    added: Artifact[]
    visibility: Record<string, { visible: boolean; action: string }>
    focus?: Artifact
    afterAction?: string
    version: number
  }>({ session: sessionId, added: [], visibility: {}, version: 0 })
  if (manual.session !== sessionId) {
    setManual({
      session: sessionId,
      baseAction: base.at(-1)?.action,
      added: [],
      visibility: {},
      version: 0,
    })
  }
  const current = useMemo(
    () =>
      manual.session === sessionId && manual.baseAction === base.at(-1)?.action
        ? manual
        : {
            session: sessionId,
            baseAction: base.at(-1)?.action,
            added: [],
            visibility: {},
            version: 0,
          },
    [manual, sessionId, base],
  )
  const layers = useMemo(() => {
    const merged = new Map(base.map((layer) => [layer.artifact.result_id, layer]))
    for (const artifact of current.added) {
      const existing = merged.get(artifact.result_id)
      merged.set(artifact.result_id, {
        artifact,
        visible: existing?.visible ?? true,
        action: existing?.action ?? '',
      })
    }
    return [...merged.values()].slice(-12).map((layer, index) => {
      const override = current.visibility[layer.artifact.result_id]
      return {
        ...layer,
        color: COLORS[index % COLORS.length],
        visible: override?.action === layer.action ? override.visible : layer.visible,
      }
    })
  }, [base, current])
  function showSelection(artifacts: Artifact[]) {
    setManual((previous) => ({
      session: sessionId,
      baseAction: base.at(-1)?.action,
      added: artifacts,
      visibility: Object.fromEntries([
        ...base.map(
          (layer) => [layer.artifact.result_id, { visible: false, action: layer.action }] as const,
        ),
        ...artifacts.map(
          (artifact) =>
            [
              artifact.result_id,
              {
                visible: true,
                action:
                  base.find((layer) => layer.artifact.result_id === artifact.result_id)?.action ??
                  '',
              },
            ] as const,
        ),
      ]),
      focus: artifacts.at(-1),
      afterAction: base.at(-1)?.action,
      version: previous.version + 1,
    }))
  }
  function show(artifact: Artifact) {
    showSelection([artifact])
  }
  function clear() {
    showSelection([])
  }
  function toggle(id: string, visible: boolean) {
    const action = layers.find((layer) => layer.artifact.result_id === id)?.action ?? ''
    setManual({ ...current, visibility: { ...current.visibility, [id]: { visible, action } } })
  }
  const features = useMemo(
    () =>
      layers
        .filter((layer) => layer.visible)
        .flatMap((layer) =>
          layer.artifact.features.map((feature) => ({
            ...feature,
            properties: { ...feature.properties, _color: layer.color },
          })),
        ),
    [layers],
  )
  const latest = base.filter((layer) => layer.visible).at(-1)
  const focus =
    current.afterAction === latest?.action &&
    current.focus &&
    current.added.some((item) => item.result_id === current.focus?.result_id)
      ? current.focus
      : latest?.artifact
  return {
    layers,
    features,
    show,
    showSelection,
    clear,
    toggle,
    focusFeatures: focus?.features,
    focusKey: `${sessionId}:${latest?.action ?? ''}:${current.version}`,
  }
}
