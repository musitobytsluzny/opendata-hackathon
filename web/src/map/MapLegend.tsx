import type { Answer } from '../chat/assistant'
import { formatValue, okresName } from '../chat/assistant'
import { Icon } from '../components/Icon'
import { OKRESY, type OkresId } from './geo'

type Props = {
  answer: Answer | null
  focused: OkresId | null
  onReset: () => void
  onHide: () => void
}
export function MapLegend({ answer, focused, onReset, onHide }: Props) {
  const rows = answer?.rows ?? []
  const values = rows.map((row) => row.value)
  const missing = Object.keys(OKRESY).length - new Set(rows.map((row) => row.okres)).size
  const value = rows.find((row) => row.okres === focused)?.value
  return (
    <section className="map-legend" aria-label="Legenda mapy">
      <div className="map-legend__head">
        <span>{answer?.sample ? 'Ukázková data' : 'Plzeňský kraj'}</span>
        <button type="button" className="icon-btn" aria-label="Skrýt legendu" onClick={onHide}>
          <Icon name="close" size={14} />
        </button>
      </div>
      <h2>{answer?.short ?? 'Mapa otevřených dat'}</h2>
      {rows.length ? (
        <>
          <p className="map-legend__metric">{answer?.metric}</p>
          <div
            className="map-legend__ramp"
            style={
              Math.min(...values) === Math.max(...values)
                ? { background: 'var(--data-low, var(--blue-1))' }
                : undefined
            }
            aria-hidden="true"
          />
          <div className="map-legend__range tabular">
            <span>{formatValue(Math.min(...values), answer?.unit, answer?.signed)}</span>
            <span>{formatValue(Math.max(...values), answer?.unit, answer?.signed)}</span>
          </div>
          <p className="map-legend__coverage">
            {rows.length} ze 7 okresů
            {missing > 0 && (
              <span>
                <i />
                {missing} bez dat
              </span>
            )}
          </p>
          {missing > 0 && <p className="map-legend__note">Chybějící hodnoty nejsou nuly.</p>}
        </>
      ) : (
        <p className="map-legend__note">
          Výsledek konverzace se zobrazí přímo v mapě. Kliknutím vyberete okres.
        </p>
      )}
      {focused && (
        <div className="map-legend__selection">
          <span>
            {okresName(focused)}
            <strong>
              {value !== undefined
                ? formatValue(value, answer?.unit, answer?.signed)
                : 'Bez dostupných dat'}
            </strong>
          </span>
          <button
            type="button"
            className="icon-btn"
            onClick={onReset}
            aria-label="Zrušit výběr okresu"
          >
            <Icon name="close" size={14} />
          </button>
        </div>
      )}
      {answer?.source && (
        <p className="map-legend__note">
          {answer.source.period} · {answer.source.publisher}
        </p>
      )}
    </section>
  )
}
