import { useEffect, useRef, useState } from 'react'
import { Icon } from '../components/Icon'
import { formatValue, okresName, type Answer } from './assistant'
import { Markdown } from './Markdown'
import type { OkresId } from '../map/geo'

export function AnswerView({
  answer,
  hovered,
  focused,
  onHover,
  onFocusOkres,
  onShow,
  onAsk,
}: {
  answer: Answer
  hovered: OkresId | null
  focused: OkresId | null
  onHover: (id: OkresId | null) => void
  onFocusOkres: (id: OkresId) => void
  onShow?: () => void
  onAsk?: (question: string) => void
}) {
  const [copied, setCopied] = useState(false)
  const [copyError, setCopyError] = useState(false)
  const copyTimer = useRef<number | undefined>(undefined)
  useEffect(() => () => window.clearTimeout(copyTimer.current), [])
  async function copy() {
    try {
      await navigator.clipboard.writeText(answer.text)
      setCopied(true)
      setCopyError(false)
      window.clearTimeout(copyTimer.current)
      copyTimer.current = window.setTimeout(() => setCopied(false), 2000)
    } catch {
      setCopyError(true)
    }
  }
  function download() {
    if (!answer.rows) return
    const cell = (value: string) => '"' + value.replace(/"/g, '""') + '"'
    const rows = [
      ['Okres', answer.metric ?? 'Hodnota', 'Jednotka', 'Zdroj', 'Období', 'Ukázková data'],
      ...answer.rows.map((row) => [
        okresName(row.okres),
        String(row.value),
        answer.unit ?? '',
        answer.source?.publisher ?? '',
        answer.source?.period ?? '',
        answer.sample ? 'ano' : 'ne',
      ]),
    ]
    const blob = new Blob(['\uFEFF' + rows.map((row) => row.map(cell).join(';')).join('\r\n')], {
      type: 'text/csv;charset=utf-8',
    })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = 'kartogram-data.csv'
    link.click()
    window.setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
  const max = Math.max(1, ...(answer.rows ?? []).map((r) => Math.abs(r.value)))
  return (
    <div className="answer">
      <div className="answer__author">
        KartogramMCP {answer.sample && <span className="answer__badge">Demo</span>}
      </div>
      <Markdown text={answer.text} />
      {answer.rows && (
        <figure className="answer__data">
          <figcaption>{answer.metric}</figcaption>
          <table className="tabular">
            <caption className="sr-only">
              {answer.metric}. Kliknutím na okres na něj přiblížíte mapu.
            </caption>
            <thead className="sr-only">
              <tr>
                <th scope="col">Okres</th>
                <th scope="col">Poměr</th>
                <th scope="col">Hodnota</th>
              </tr>
            </thead>
            <tbody>
              {answer.rows.map((r) => (
                <tr
                  key={r.okres}
                  className={
                    [
                      hovered === r.okres ? 'is-hovered' : '',
                      focused === r.okres ? 'is-focused' : '',
                    ]
                      .filter(Boolean)
                      .join(' ') || undefined
                  }
                  onMouseEnter={() => onHover(r.okres)}
                  onMouseLeave={() => onHover(null)}
                  onClick={() => onFocusOkres(r.okres)}
                >
                  <th scope="row">
                    <button
                      type="button"
                      className="okres-btn"
                      aria-pressed={focused === r.okres}
                      aria-label={
                        focused === r.okres
                          ? `${okresName(r.okres)}, ${formatValue(r.value, answer.unit, answer.signed)}. Zpět na celý kraj`
                          : `${okresName(r.okres)}, ${formatValue(r.value, answer.unit, answer.signed)}. Přiblížit mapu na okres`
                      }
                      onFocus={() => onHover(r.okres)}
                      onBlur={() => onHover(null)}
                      onClick={(e) => {
                        e.stopPropagation()
                        onFocusOkres(r.okres)
                      }}
                    >
                      {okresName(r.okres)}
                    </button>
                  </th>
                  <td className="answer__bar" aria-hidden="true">
                    <span
                      className={r.value < 0 ? 'bar bar--neg' : 'bar'}
                      style={{ width: `${(Math.abs(r.value) / max) * 100}%` }}
                    />
                  </td>
                  <td className="answer__val">
                    {formatValue(r.value, answer.unit, answer.signed)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </figure>
      )}
      {answer.source && (
        <p className="source">
          <Icon name="database" size={16} />
          <span>
            <span className="sr-only">Zdroj dat: </span>
            {answer.source.publisher} · {answer.source.name} · {answer.source.period}
          </span>
        </p>
      )}
      {onShow && (
        <button type="button" className="show-on-map" onClick={onShow}>
          <Icon name="locate" size={16} />
          Zobrazit na mapě
        </button>
      )}
      <div className="answer__actions">
        <button type="button" onClick={copy}>
          {copied ? 'Zkopírováno' : 'Kopírovat odpověď'}
        </button>
        {answer.rows?.length ? (
          <button type="button" onClick={download}>
            Stáhnout CSV
          </button>
        ) : null}
      </div>
      {copyError && (
        <p className="sample" role="status">
          Kopírování není dostupné. Text můžete označit a zkopírovat ručně.
        </p>
      )}
      {onAsk && answer.rows?.length ? (
        <div className="answer__followups" aria-label="Navazující dotazy">
          <button
            type="button"
            onClick={() =>
              onAsk(
                `Vysvětli rozdíly mezi okresy u metriky ${answer.metric}. Použij pouze dostupná data.`,
              )
            }
          >
            Vysvětlit rozdíly
          </button>
          <button type="button" onClick={() => onAsk('Jaké je pokrytí obcí a omezení těchto dat?')}>
            Pokrytí a omezení dat
          </button>
        </div>
      ) : null}
      {answer.sample && (
        <p className="sample">Ukázková data, napojení na skutečné zdroje se připravuje.</p>
      )}
    </div>
  )
}
