import { cn } from "@ezo/ui";
/** Decorative echo of the energy presence; no robot eyes, mouth or skin. */
export function EnergyMark({ size = 32, className }: { size?: number; className?: string }) {
  return <svg width={size} height={size} viewBox="0 0 32 32" fill="none" aria-hidden="true" className={cn("shrink-0", className)}>
    {[0,1,2,3,4,5,6].map((i) => <path key={i} d={`M ${12-i*.62} ${5+i*2} Q 16 ${3+i*2} ${20+i*.62} ${5+i*2}`} stroke={i>1&&i<5?"#ffb347":"#40d9ff"} strokeWidth="0.8" opacity={.9-i*.07} />)}
    <path d="M12 18v3L6 25l-2 5M20 18v3l6 4 2 5M9 24q7 3 14 0M8 27q8 3 16 0" stroke="#40d9ff" strokeWidth=".8" opacity=".8" />
  </svg>;
}
