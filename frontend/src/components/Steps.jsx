const STEPS = [
  { id: 'import', label: 'Import' },
  { id: 'cut', label: 'Cut' },
  { id: 'reframe', label: 'Reframe' },
  { id: 'export', label: 'Export' },
]

// Where the user is in Import -> Cut -> Reframe -> Export. Steps before the current one show as done.
export default function Steps({ current }) {
  const currentIndex = STEPS.findIndex((s) => s.id === current)
  return (
    <nav className="steps" aria-label="Progress">
      <ol>
        {STEPS.map((step, i) => {
          const state = i < currentIndex ? 'done' : i === currentIndex ? 'current' : 'todo'
          return (
            <li key={step.id} className={`step step--${state}`} aria-current={state === 'current' ? 'step' : undefined}>
              <span className="step-num" aria-hidden="true">
                {String(i + 1).padStart(2, '0')}
              </span>
              {step.label}
              {state === 'done' && <span className="visually-hidden"> (done)</span>}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
