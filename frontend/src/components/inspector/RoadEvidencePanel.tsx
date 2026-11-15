import type { RoadEvidence } from '../../services/roadEvidence'

// The evidence behind one road stretch, laid out so a reviewer can explain it in about 30 seconds: which stretch, why it is
// rated as it is, what the radar could see there and from which file, and what to check next. Exports use the same record.
export function RoadEvidencePanel({ ev }: { ev: RoadEvidence }) {
  return (
    <details className="road-evidence">
      <summary>Evidence for this stretch</summary>
      <dl className="ev-facts">
        <dt>Stretch</dt><dd className="mono">{ev.id ?? 'No ID in this build'}</dd>
        {ev.name && <><dt>Name</dt><dd>{ev.name}</dd></>}
        <dt>Road</dt><dd>{ev.road}{ev.bridge ? ', bridge' : ''}, {ev.lengthM} m long</dd>
        {ev.osmWay && <><dt>OSM way</dt><dd className="mono">{ev.osmWay}</dd></>}
        <dt>Rating</dt><dd>{ev.exposure} exposure{ev.reasons.length ? `: ${ev.reasons.join('; ')}` : ': no factor found'}</dd>
        {ev.radar.pair && <><dt>Radar pair</dt><dd>{ev.radar.pair}{ev.radar.trackFrame ? `, ${ev.radar.trackFrame}` : ''}</dd></>}
        {ev.radar.baseline && <><dt>Before pair</dt><dd>{ev.radar.baseline}</dd></>}
        {ev.radar.granule && <><dt>Source file</dt><dd className="mono wrap">{ev.radar.granule}</dd></>}
        <dt>Observability</dt><dd>Method version {ev.radar.methodVersion}{ev.radar.current ? '' : ' (withdrawn; awaiting the rebuild)'}. {ev.radar.watch}.</dd>
      </dl>
      <table className="shares">
        <caption>What the radar could see along this stretch</caption>
        <tbody>{ev.radar.shares.map((s) => <tr key={s.label}><th scope="row">{s.label}</th><td>{s.pct === null ? 'not in this build' : `${s.pct}%`}</td></tr>)}</tbody>
      </table>
      <p className="small"><strong>Context</strong></p>
      <ul className="small">{ev.context.map((c) => <li key={c}>{c}</li>)}</ul>
      <p className="small"><strong>What to verify</strong></p>
      <ul className="small">{ev.verify.map((v) => <li key={v}>{v}</li>)}</ul>
    </details>
  )
}
