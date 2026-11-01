// The wordmark: a 16:9 frame turning into a 9:16 one, then the name. Same mark as public/favicon.svg.
export default function Logo() {
  return (
    <span className="wordmark">
      <svg className="wordmark-mark" viewBox="0 0 24 16" width="24" height="16" aria-hidden="true">
        <rect x="1" y="4.5" width="10" height="7" rx="1" fill="none" stroke="currentColor" strokeWidth="1.5" />
        <path d="M12.5 3.5a4 4 0 0 1 3.5 2" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
        <rect x="16.5" y="2" width="6" height="12" rx="1" fill="var(--accent)" />
      </svg>
      <span className="wordmark-name">FlipClip</span>
    </span>
  )
}
