export function LogoMark({ size = 24 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect width="24" height="24" rx="6" fill="#000000" />
      <rect
        x="0.5"
        y="0.5"
        width="23"
        height="23"
        rx="5.5"
        stroke="rgba(255,255,255,0.18)"
        strokeWidth="1"
      />
      <path
        d="M6 12l4 4 8-8"
        stroke="#ffffff"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}
