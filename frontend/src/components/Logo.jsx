// A wide frame flipping into a tall one. Same drawing as public/favicon.svg.
export default function Logo() {
  return (
    <svg className="logo" viewBox="0 0 32 32" width="32" height="32" aria-hidden="true">
      <rect width="32" height="32" rx="8" fill="var(--accent)" />
      <rect x="5" y="11" width="13" height="9" rx="1.5" fill="none" stroke="#fff" strokeWidth="2" opacity="0.55" />
      <rect x="17" y="7" width="9" height="16" rx="1.5" fill="#fff" />
    </svg>
  )
}
