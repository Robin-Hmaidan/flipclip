const STEPS = [
  { id: 'input', label: 'Input' },
  { id: 'clips', label: 'Clips' },
  { id: 'edit', label: 'Edit' },
  { id: 'export', label: 'Export' },
]

// Where the user is in Input -> Clips -> Edit -> Export. Steps before the current one show as done.
export default function Steps({ current }) {
  const currentIndex = STEPS.findIndex((s) => s.id === current)
  return (
    <nav aria-label="Progress">
      <ol className="steps">
        {STEPS.map((step, i) => {
          const state = i < currentIndex ? 'done' : i === currentIndex ? 'current' : 'todo'
          return (
            <li key={step.id} className={`step step--${state}`} aria-current={state === 'current' ? 'step' : undefined}>
              <span className="step-dot" aria-hidden="true">
                {state === 'done' ? '✓' : i + 1}
              </span>
              <span className="step-label">
                {step.label}
                {state === 'done' && <span className="visually-hidden"> (done)</span>}
              </span>
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
