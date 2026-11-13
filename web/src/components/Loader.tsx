export function Loader({ label = 'Načítám…' }: { label?: string }) {
  return (
    <div className="loader" role="status">
      <svg viewBox="-2 -2 84.4 104" aria-hidden="true">
        <use className="loader__track" href="#kraj-outline" />
        <use className="loader__run" href="#kraj-outline" />
      </svg>
      <span>{label}</span>
    </div>
  )
}
