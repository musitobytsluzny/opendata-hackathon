import { useId, type ReactNode } from 'react'

type Option<T extends string> = { value: T; label: string; swatch?: ReactNode }

export function Choice<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string
  value: T
  options: readonly Option<T>[]
  onChange: (value: T) => void
}) {
  const id = useId()
  return (
    <div className="choice" role="radiogroup" aria-labelledby={id}>
      <span className="choice__label" id={id}>
        {label}
      </span>
      <span className="choice__options">
        {options.map((option) => (
          <label key={option.value} className="choice__option">
            <input
              type="radio"
              name={id}
              checked={option.value === value}
              onChange={() => onChange(option.value)}
            />
            <span>
              {option.swatch}
              {option.label}
            </span>
          </label>
        ))}
      </span>
    </div>
  )
}

export function Toggle({
  label,
  checked,
  onChange,
}: {
  label: string
  checked: boolean
  onChange: (checked: boolean) => void
}) {
  return (
    <label className="switch">
      <span className="switch__label">{label}</span>
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span className="switch__track" aria-hidden="true" />
    </label>
  )
}
