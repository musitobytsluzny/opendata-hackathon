import { useMemo, useState } from 'react'
import type { Artifact } from './assistant'
import { formatValue } from './assistant'
import './ResultView.css'

export function ResultView({
  artifact,
  onMap,
}: {
  artifact: Artifact
  onMap: (artifact: Artifact) => void
}) {
  const numeric = artifact.columns.filter((column) => column.numeric)
  const [view, setView] = useState(artifact.view === 'map' ? 'table' : artifact.view)
  const [valueKey, setValueKey] = useState(artifact.value_key ?? numeric[0]?.key ?? '')
  const labelKey =
    artifact.label_key ??
    artifact.columns.find((column) => !column.numeric && column.key !== 'id')?.key ??
    artifact.columns[0]?.key ??
    ''
  const [sort, setSort] = useState<{ key: string; descending: boolean } | null>(null)
  const rows = useMemo(
    () =>
      sort
        ? artifact.rows.toSorted((a, b) => {
            const first = a[sort.key],
              second = b[sort.key]
            if (first === null || first === undefined) return 1
            if (second === null || second === undefined) return -1
            const difference =
              typeof first === 'number' && typeof second === 'number'
                ? first - second
                : String(first).localeCompare(String(second), 'cs')
            return difference * (sort.descending ? -1 : 1)
          })
        : artifact.rows,
    [artifact.rows, sort],
  )
  const points = rows
    .filter((row) => typeof row[valueKey] === 'number')
    .map((row) => ({ label: String(row[labelKey] ?? ''), value: row[valueKey] as number }))
  const low = Math.min(0, ...points.map((point) => point.value)),
    high = Math.max(0, ...points.map((point) => point.value))
  const span = high - low || 1
  const unit = artifact.columns.find((column) => column.key === valueKey)?.unit ?? ''
  const format = (value: unknown, key: string) =>
    typeof value === 'number'
      ? formatValue(value, artifact.columns.find((column) => column.key === key)?.unit)
      : value === null || value === undefined
        ? '—'
        : String(value)
  function download() {
    const cell = (value: unknown) => {
      let text = value == null ? '' : String(value)
      if (/^[=+@\-\t\r]/.test(text) && typeof value !== 'number') text = "'" + text
      return '"' + text.replaceAll('"', '""') + '"'
    }
    const text = [
      artifact.columns.map((column) => column.label + (column.unit ? ` (${column.unit})` : '')),
      ...rows.map((row) => artifact.columns.map((column) => row[column.key])),
    ]
      .map((row) => row.map(cell).join(';'))
      .join('\r\n')
    const url = URL.createObjectURL(new Blob(['\uFEFF' + text], { type: 'text/csv;charset=utf-8' }))
    const link = document.createElement('a')
    link.href = url
    link.download = 'kartogram-vysledek.csv'
    link.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
  return (
    <figure className="result-view">
      <figcaption>
        {artifact.title}
        {artifact.sample && <span className="answer__badge">Demo</span>}
      </figcaption>
      <div className="result-view__controls" aria-label="Zobrazení výsledku">
        <button type="button" aria-pressed={view === 'table'} onClick={() => setView('table')}>
          Tabulka
        </button>
        {numeric.length > 0 && (
          <>
            <button type="button" aria-pressed={view === 'bar'} onClick={() => setView('bar')}>
              Sloupce
            </button>
            <button type="button" aria-pressed={view === 'line'} onClick={() => setView('line')}>
              Spojnice
            </button>
          </>
        )}
        {artifact.features.length > 0 && (
          <button type="button" onClick={() => onMap(artifact)}>
            Zobrazit na mapě
          </button>
        )}
        <button type="button" onClick={download} disabled={!rows.length}>
          CSV
        </button>
      </div>
      {view !== 'table' && numeric.length > 1 && (
        <label>
          Metrika{' '}
          <select value={valueKey} onChange={(event) => setValueKey(event.target.value)}>
            {numeric.map((column) => (
              <option key={column.key} value={column.key}>
                {column.label}
              </option>
            ))}
          </select>
        </label>
      )}
      {!rows.length ? (
        <p role="status">Pro tento dotaz nejsou dostupná data.</p>
      ) : view === 'table' ? (
        <div className="answer__table-wrap">
          <table className="tabular">
            <caption className="sr-only">{artifact.title}</caption>
            <thead>
              <tr>
                {artifact.columns.map((column) => (
                  <th
                    key={column.key}
                    scope="col"
                    aria-sort={
                      sort?.key === column.key
                        ? sort.descending
                          ? 'descending'
                          : 'ascending'
                        : 'none'
                    }
                  >
                    <button
                      type="button"
                      aria-label={`Seřadit podle: ${column.label}`}
                      onClick={() =>
                        setSort({
                          key: column.key,
                          descending: sort?.key === column.key ? !sort.descending : column.numeric,
                        })
                      }
                    >
                      {column.label}
                      {sort?.key === column.key ? (sort.descending ? ' ↓' : ' ↑') : ''}
                    </button>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => (
                <tr key={String(row.id ?? index)}>
                  {artifact.columns.map((column, ci) => (
                    <td key={column.key}>
                      {ci === 0 && artifact.features.some((feature) => feature.id === row.id) ? (
                        <button
                          type="button"
                          className="okres-btn"
                          onClick={() =>
                            onMap({
                              ...artifact,
                              title: String(row[column.key] ?? artifact.title),
                              features: artifact.features.filter(
                                (feature) => feature.id === row.id,
                              ),
                            })
                          }
                        >
                          {format(row[column.key], column.key)}
                        </button>
                      ) : (
                        format(row[column.key], column.key)
                      )}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : view === 'bar' ? (
        <div
          className="result-view__bars"
          role="img"
          aria-label={`${artifact.title}, sloupcový graf`}
        >
          {points.map((point, index) => (
            <div className="result-view__bar-row" key={index}>
              <span>{point.label}</span>
              <div className="result-view__track">
                <i
                  style={{
                    left: `${((Math.min(0, point.value) - low) / span) * 100}%`,
                    width: `${(Math.abs(point.value) / span) * 100}%`,
                  }}
                />
              </div>
              <strong>{formatValue(point.value, unit)}</strong>
            </div>
          ))}
        </div>
      ) : (
        <>
          <svg
            className="result-view__line"
            viewBox="0 0 640 230"
            role="img"
            aria-label={`${artifact.title}, spojnicový graf`}
          >
            <title>
              {points
                .map((point) => `${point.label}: ${formatValue(point.value, unit)}`)
                .join('; ')}
            </title>
            <line
              x1="20"
              y1={200 - (-low / span) * 170}
              x2="620"
              y2={200 - (-low / span) * 170}
              stroke="currentColor"
              opacity=".25"
            />
            <polyline
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              points={points
                .map(
                  (point, index) =>
                    `${20 + (index / Math.max(1, points.length - 1)) * 600},${200 - ((point.value - low) / span) * 170}`,
                )
                .join(' ')}
            />
            {points.map((point, index) => (
              <circle
                key={index}
                cx={20 + (index / Math.max(1, points.length - 1)) * 600}
                cy={200 - ((point.value - low) / span) * 170}
                r="3"
                fill="currentColor"
              >
                <title>
                  {point.label}: {formatValue(point.value, unit)}
                </title>
              </circle>
            ))}
          </svg>
          <p className="result-view__note">
            Pořadí podle tabulky; spojnice sama o sobě neznamená časový vývoj. Přesné hodnoty
            najdete v tabulce.
          </p>
        </>
      )}
      {artifact.note && <p className="result-view__note">{artifact.note}</p>}
      {artifact.sources.length > 0 && (
        <p className="source">
          {artifact.sources
            .map((source) => source.name ?? source.table_name)
            .filter(Boolean)
            .join(' · ')}
        </p>
      )}
    </figure>
  )
}
