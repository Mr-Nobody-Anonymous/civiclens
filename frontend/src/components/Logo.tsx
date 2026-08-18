/* CivicLens brand mark — an aperture iris (lens = seeing, transparency) whose
   six blades form a community circle around a golden focal point (the issue
   brought into focus). One gold blade = the citizen spotlight. Colors: deep
   forest + CivicLens greens with the warm Ethiopian gold, used as accents. */

const BLADES = [
  'M 5.36,-43.67 A 44 44 0 0 1 39.72,-18.95 L 26.86,-2.75 A 27 27 0 0 0 8.85,-25.51 Z',
  'M 40.51,-17.18 A 44 44 0 0 1 34.36,24.72 L 13.72,23.25 A 27 27 0 0 0 24.29,-11.79 Z',
  'M 35.15,26.49 A 44 44 0 0 1 -5.36,43.67 L -13.14,24.46 A 27 27 0 0 0 21.45,16.37 Z',
  'M -5.36,43.67 A 44 44 0 0 1 -39.72,18.95 L -26.86,2.75 A 27 27 0 0 0 -8.85,25.51 Z',
  'M -40.51,17.18 A 44 44 0 0 1 -34.36,-24.72 L -13.72,-23.25 A 27 27 0 0 0 -24.29,11.79 Z',
  'M -35.15,-26.49 A 44 44 0 0 1 5.36,-43.67 L 8.85,-25.51 A 27 27 0 0 0 -15.65,-22.01 Z',
]

const COLOR = ['#F4B942', '#0A3D2C', '#17A05E', '#0c7d48', '#0A3D2C', '#17A05E']
const DARK = ['#F4B942', '#8FDBB4', '#2FBF77', '#8FDBB4', '#DFF5EA', '#2FBF77']

export function LogoMark({ size = 36, variant = 'auto', spin = false, className = '' }: {
  size?: number; variant?: 'auto' | 'color' | 'dark' | 'mono'; spin?: boolean; className?: string
}) {
  const colors = variant === 'dark' ? DARK : variant === 'mono' ? Array(6).fill('currentColor') : COLOR
  const darkColors = variant === 'color' ? COLOR : DARK
  return (
    <svg viewBox="-52 -52 104 104" width={size} height={size} aria-hidden className={className}>
      <g className={spin ? 'animate-iris origin-center' : undefined} style={spin ? { transformBox: 'fill-box' } : undefined}>
        {BLADES.map((d, i) => (
          <path key={i} d={d}
            className={variant === 'auto' ? 'dark:hidden' : undefined}
            fill={colors[i]} />
        ))}
        {variant === 'auto' && BLADES.map((d, i) => (
          <path key={`d${i}`} d={d} className="hidden dark:inline" fill={darkColors[i]} />
        ))}
      </g>
      <circle r="10.5" fill={variant === 'mono' ? 'currentColor' : '#F4B942'} />
    </svg>
  )
}

export function LogoLockup({ size = 34, sub = true, light = false }: { size?: number; sub?: boolean; light?: boolean }) {
  return (
    <span className="inline-flex items-center gap-2.5">
      <LogoMark size={size} variant={light ? 'dark' : 'auto'} />
      <span className="leading-none">
        <span className={`block text-[1.15rem] font-extrabold tracking-tight ${light ? 'text-white' : 'text-ink-900 dark:text-white'}`}>
          Civic<span className={light ? 'text-brand-300' : 'text-brand-600 dark:text-brand-300'}>Lens</span>
        </span>
        {sub && <span className="mt-0.5 block text-[9px] font-bold tracking-[0.35em] text-gold-600 dark:text-gold-400">ETHIOPIA</span>}
      </span>
    </span>
  )
}
