import type { Evidence, Verification } from '../model'
import { evidenceLabels } from '../research'
import { Badge } from './ui/badge'

const verificationLabels: Record<Verification, string> = {
  unverified: '未核实', verified: '已核实', disputed: '存在争议',
}

export function EvidenceSections({ evidence }: { evidence: Evidence[] }) {
  return evidence.map((item) => (
    <section className={`evidence-row evidence-row--${item.category}`} key={item.id}>
      <h4><Badge tone={item.category}>{evidenceLabels[item.category]}</Badge>
        {item.verification && <span className="verification">{verificationLabels[item.verification]}</span>}
      </h4>
      <p>{item.text}</p>
      {item.category === 'inference' && <small>依据　{item.evidence}<br />来源 ID　{item.source_post_ids.join('、')}</small>}
    </section>
  ))
}

