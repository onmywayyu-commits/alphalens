import type { BriefRunData, Dashboard } from './model.ts'
import { groupSignalEvidence, reviewedSignal } from './signal-card.ts'

const watchlist = [
  {
    id: 'essd-purchase-timing', name: '企业级 SSD', topic: '存储供需',
    support: 'GPU 到货改善后，企业级 SSD 新订单先企稳，随后出货或收入指引改善。',
    challenge: 'GPU 到货恢复后，新订单和出货仍弱，需重新评估需求转弱或供应商份额变化。',
    caveat: '多条陈述来自 Serenity 的同一条存档，引用指向同一个来源。',
  },
  {
    id: 'optical-order-conversion', name: '光互连', topic: '光互连',
    support: '合同出现明确的采购义务，并有同口径的付费出货或交付进展。',
    challenge: '最低采购义务缺失、订单取消或交付一再延后，会削弱收入可见度的判断。',
    caveat: '两条起始存档来自同一作者。',
  },
  {
    id: 'liquid-rack-retrofit', name: '液冷机房', topic: '数据中心基础设施',
    support: '站点额定荷载低于满载要求，需要加固，且有相应改造成本或停机周期。',
    challenge: '现有楼板达到要求，或调整机架密度后仍可按期交付且单位成本具竞争力。',
    caveat: '17–19 行来自同一线程，工程参数仍待与设备规格和站点资料核对。',
  },
]

export const isRadarThesis = (eventKey: string) => watchlist.some(({ id }) => id === eventKey)

export type RadarEvidenceGroup = ReturnType<typeof groupSignalEvidence>
interface RadarEntry {
  date: string
  kind: 'initial' | 'follow_up' | 'context'
  groups: RadarEvidenceGroup[]
  support: string[]
  counter: string[]
  statements?: Record<string, string>
}

function entry(
  run: BriefRunData, kind: RadarEntry['kind'], ids: string[], relations: Dashboard['relations'],
  support: string[] = [], counter: string[] = [], seen = new Set<string>(),
): RadarEntry | null {
  const records = groupSignalEvidence(run.evidence, ids).filter(({ recordId }) => !seen.has(recordId))
  if (!records.length) return null

  const parents = new Map(records.map(({ recordId }) => [recordId, recordId]))
  function rootOf(recordId: string): string {
    const parent = parents.get(recordId) ?? recordId
    return parent === recordId ? recordId : rootOf(parent)
  }
  function merge(recordIds: string[]) {
    const roots = [...new Set(recordIds.filter((id) => parents.has(id)).map(rootOf))]
    for (const id of roots.slice(1)) parents.set(id, roots[0])
  }

  const samePost = new Map<string, string[]>()
  for (const record of records) {
    for (const { citations } of record.items) {
      for (const cite of citations) {
        if (!cite.source_post_id || cite.kind === 'quote') continue
        const matches = samePost.get(cite.source_post_id) ?? []
        matches.push(record.recordId)
        samePost.set(cite.source_post_id, matches)
      }
    }
  }
  for (const matches of samePost.values()) merge(matches)
  for (const relation of relations ?? []) {
    if (relation.kind !== 'archive_quote') merge(relation.record_ids)
  }

  const groups = new Map<string, RadarEvidenceGroup>()
  for (const record of records.sort((a, b) => a.excelRow - b.excelRow)) {
    const id = rootOf(record.recordId)
    const group = groups.get(id) ?? []
    group.push(record)
    groups.set(id, group)
  }
  return { date: run.date, kind, groups: [...groups.values()], support, counter }
}

export function radarTheses(data: Dashboard) {
  if (data.mode !== 'research') return []
  const runs = (data.brief_runs ?? []).filter((run) => run.mode !== 'rehearsal' && run.daily_v2)
    .sort((a, b) => a.date.localeCompare(b.date))

  return watchlist.flatMap((watch) => {
    const timeline: RadarEntry[] = []
    const includedRecords = new Set<string>()
    let baseline: { run: BriefRunData; signal: NonNullable<BriefRunData['daily_v2']>['top_signals'][number] } | undefined

    for (const run of runs) {
      const signal = run.daily_v2?.top_signals.find((signal) => signal.event_key === watch.id)
      if (signal) {
        const ids = [...signal.what_happened, ...signal.bull_case, ...signal.bear_case]
        const update = entry(run, baseline ? 'follow_up' : 'initial', ids, data.relations, signal.bull_case, signal.bear_case, includedRecords)
        if (update) {
          baseline ??= { run, signal }
          update.statements = reviewedSignal(run.run_id, watch.id)?.statements
          timeline.push(update)
          for (const group of update.groups) for (const record of group) includedRecords.add(record.recordId)
        }
      } else if (watch.id === 'optical-order-conversion' && run.date === '2026-11-20' && baseline) {
        // This opinion is relevant context for the case, not evidence of order conversion.
        const theme = run.daily_v2?.research_themes.find(({ theme_key }) => theme_key === 'optical-interconnect')
        const item = theme?.item_ids.includes('optical-value') && run.evidence['optical-value']
        const update = item && item.category === 'opinion' ? entry(run, 'context', ['optical-value'], data.relations) : null
        if (update) timeline.push(update)
      }
    }
    if (!baseline) return []
    const { run, signal } = baseline
    const copy = reviewedSignal(run.run_id, watch.id)
    const companyScope = copy?.companyScope ?? signal.company_scope
    return [{
      ...watch, date: run.date, latestDate: timeline.at(-1)?.date ?? run.date, timeline,
      title: copy?.title ?? signal.title, status: 'to_validate' as const,
      thesis: copy?.implication ?? signal.investment_implication,
      action: copy?.action ?? [signal.next_research_action],
      related: [...new Set(companyScope ? [...companyScope.direct, ...companyScope.value_chain] : signal.related_tickers)],
      sectors: signal.related_sectors, companyScope,
    }]
  })
}

export function filterRadar(theses: ReturnType<typeof radarTheses>, query: string, topic: string, status: string) {
  const normalize = (value: string) => value.normalize('NFKC').toLowerCase()
  const terms = normalize(query).trim().split(/\s+/).filter(Boolean)
  return theses.filter((thesis) => {
    const searchable = normalize([thesis.name, thesis.title, thesis.topic, ...thesis.related, ...thesis.sectors].join(' '))
    return (!topic || topic === thesis.topic) && (!status || status === thesis.status) &&
      terms.every((term) => searchable.includes(term))
  })
}
