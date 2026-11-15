// Short labels for saved time steps, for chart axes. A step is a date ("2026-08-16"), a pair of dates ("2026-08-16/2026-08-28"),
// or an hour ("06 UTC", from the retired weather case). Anything else is shown as given.
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const ISO = /^(\d{4})-(\d{2})-(\d{2})/

function day(s: string): { d: number; m: string } | null {
  const x = ISO.exec(s)
  return x ? { d: Number(x[3]), m: MONTHS[Number(x[2]) - 1] } : null
}

export function stepLabel(label: string): string {
  const [a, b] = label.split('/')
  const da = day(a), db = b ? day(b) : null
  if (da && db) return da.m === db.m ? `${da.d}–${db.d} ${db.m}` : `${da.d} ${da.m}–${db.d} ${db.m}`
  if (da) return `${da.d} ${da.m}`
  return label.length > 8 ? label.slice(0, 8) : label
}

// What the chart's x-axis spans, for its caption
export function stepKind(labels: string[]): 'dates' | 'pairs' | 'hours' | 'steps' {
  if (labels.every((l) => l.includes('/') && l.split('/').every((p) => ISO.test(p)))) return 'pairs'
  if (labels.every((l) => ISO.test(l))) return 'dates'
  if (labels.every((l) => /^\d{2}\b/.test(l))) return 'hours'
  return 'steps'
}
