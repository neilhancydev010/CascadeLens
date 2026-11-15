import { EVIDENCE, type EvidenceClass } from '../../services/evidence'

export function EvidenceTag({ kind, compact = false }: { kind: EvidenceClass; compact?: boolean }) {
  const e = EVIDENCE[kind]
  return <span className={`evidence ev-${kind}${compact ? ' compact' : ''}`} title={e.meaning}>{e.label}</span>
}
