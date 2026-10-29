import type { JSX } from "react"; // The decorative background of the sign-in pages (login, forgot / reset password, and
// so the page you land on after signing out). Purely visual: hidden from assistive
// technology, not clickable, nothing focusable. Styles are in styles/globals.css
// ("Auth pages background"): token colours only, CSS-only motion that stops under
// prefers-reduced-motion, and everything hidden in forced-colors mode.

/** A week on a calendar: header row, 7 columns, 5 rows, a few "filled" days. */
function CalendarMotif({ className }: { className: string }): JSX.Element {
  const cols = Array.from({ length: 8 }, (_, i) => 20 + i * 60);
  const rows = Array.from({ length: 6 }, (_, i) => 90 + i * 60);
  return (
    <svg viewBox="0 0 460 420" fill="none" className={className}>
      <rect x="10" y="20" width="440" height="390" rx="24" stroke="currentColor" strokeWidth="3" />
      <path d="M10 80H450" stroke="currentColor" strokeWidth="3" />
      <path d="M110 6V40M350 6V40" stroke="currentColor" strokeWidth="6" strokeLinecap="round" />
      {cols.slice(1, -1).map((x) => (
        <path key={`c${x}`} d={`M${x} 80V410`} stroke="currentColor" strokeWidth="1.5" />
      ))}
      {rows.slice(1, -1).map((y) => (
        <path key={`r${y}`} d={`M10 ${y}H450`} stroke="currentColor" strokeWidth="1.5" />
      ))}
      {[
        [80, 90],
        [140, 90],
        [200, 90],
        [260, 150],
        [80, 210],
      ].map(([x, y]) => (
        <rect
          key={`${x}-${y}`}
          x={x + 8}
          y={y + 8}
          width="44"
          height="44"
          rx="8"
          fill="currentColor"
          opacity="0.5"
        />
      ))}
    </svg>
  );
}

/** A clock ring with hour ticks and hands. */
function ClockMotif({ className }: { className: string }): JSX.Element {
  const ticks = Array.from({ length: 12 }, (_, i) => (i * Math.PI) / 6);
  return (
    <svg viewBox="0 0 400 400" fill="none" className={className}>
      <circle cx="200" cy="200" r="180" stroke="currentColor" strokeWidth="3" />
      <circle cx="200" cy="200" r="150" stroke="currentColor" strokeWidth="1.5" />
      {ticks.map((a) => (
        <path
          key={a}
          d={`M${200 + 150 * Math.sin(a)} ${200 - 150 * Math.cos(a)}L${200 + 132 * Math.sin(a)} ${200 - 132 * Math.cos(a)}`}
          stroke="currentColor"
          strokeWidth="4"
          strokeLinecap="round"
        />
      ))}
      <path
        d="M200 200V95M200 200L270 240"
        stroke="currentColor"
        strokeWidth="8"
        strokeLinecap="round"
      />
      <circle cx="200" cy="200" r="10" fill="currentColor" />
    </svg>
  );
}

export function AuthBackground(): JSX.Element {
  return (
    <div
      aria-hidden="true"
      data-testid="auth-background"
      className="auth-bg pointer-events-none absolute inset-0 -z-10 overflow-hidden"
    >
      <div className="auth-bg-mesh absolute inset-0" />
      <div className="auth-bg-grid absolute inset-0" />
      <div className="auth-bg-blob auth-bg-blob-1" />
      <div className="auth-bg-blob auth-bg-blob-2" />
      <div className="auth-bg-blob auth-bg-blob-3" />
      <CalendarMotif className="auth-bg-motif absolute -bottom-28 -left-24 hidden w-[clamp(18rem,32vw,30rem)] sm:block" />
      <ClockMotif className="auth-bg-motif absolute -top-24 -right-20 hidden w-[clamp(14rem,24vw,24rem)] sm:block" />
    </div>
  );
}
