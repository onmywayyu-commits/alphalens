import type { BriefRunData, Post } from './model.ts'
import { postDay, recordKey } from './research.ts'
import { reviewedSignal, type SignalCopy } from './signal-card.ts'

export interface SignalPreview extends SignalCopy {
  title: string
  evidence: string[]
  context?: string[]
  support?: string[]
  criteria?: Record<string, { level: number; reason: string }>
  status?: 'records_verified' | 'partially_verified' | 'pending'
  action: string[]
  counter: string[]
  tags: string[]
  companies?: string[]
}

const edition = import.meta.env.DEV ? {
  runId: '55825d7def6c2a53e083a6220ec1cb41cd4c7c87232404423afe04a1c92ca7f2',
  lead: '光互连的订单承诺，到了要看兑现的时候',
  explanation: '存档同时提到光子 SOI 产能预留、近封装光学量产进度和 Coherent 回购。最值得追踪的是协议能否转成付费出货，以及量产何时进入收入和利润率。',
  tags: ['光互连', 'Soitec', 'Coherent · COHR'],
  signals: [
    {
      title: '光互连的产能预留能否转化为收入？',
      evidence: ['soitec-agreement-claim', 'npo-ramp-claim', 'optics-valuation-opinion', 'cohr-buyback-claim'],
      why: '如果预留产能有对应采购义务，供应商未来几个财年的收入可见度可能上升。量产爬坡的良率和交付节奏将决定利润率能否同步改善。',
      implication: '跟踪光子 SOI 与近封装光学从产能预留到订单、出货、确认收入的转化过程。',
      risk: '回购授权和实际执行可能有时差，合同名义金额也可能分多年兑现。光学侧线索集中在同一作者。',
      action: ['查阅公司公告和财报会，核对最低采购义务、取消条款和预计首个收入确认财年。'],
      counter: [],
      reason: '有合同与量产两条线索，可落到订单、收入和毛利三个验证指标。',
      tags: ['光互连', 'Soitec', 'Coherent · COHR'],
    },
    {
      title: 'AI 用量增长能否与云厂商资本开支脱钩？',
      evidence: ['cloud-spend-opinion', 'cloud-efficiency-argument'],
      why: '如果设备降价和利用率提升快于新增算力需求，云厂商可能以更低支出满足增长。这会影响上游按资本开支外推硬件收入的假设。',
      implication: '将云厂商算力扩张拆成设备单价、集群利用率和新增部署规模三项持续跟踪。',
      risk: '单个账号对一家公司的解读只能作为线索。推理需求超预期时，新增部署仍可能抵消效率提升。',
      action: ['把腾讯最新资本开支指引与设备价格、集群利用率和同业扩容计划逐项对照。'],
      counter: [],
      reason: '资本开支路径直接关联上游收入预期，且可用公司指引和设备价格交叉验证。',
      tags: ['云基础设施', '腾讯'],
    },
  ] satisfies SignalPreview[],
  themes: [
    { title: '光互连订单与量产', tags: ['Soitec', 'Coherent · COHR'], evidence: ['cohr-buyback-claim', 'soitec-agreement-claim', 'npo-ramp-claim'], text: '存档同时出现资本配置、产能预留与量产三类线索。' },
    { title: '云厂商 AI 资本开支', tags: ['腾讯'], evidence: ['cloud-spend-opinion'], text: '作者关注效率提升与硬件降价对后续投资强度的影响。' },
  ],
  update: { id: 'mlcc-bottleneck-opinion', title: '关注 2027 年 MLCC 供给', industry: '电子元件' },
} : null

export function briefLayout(run: BriefRunData, posts: Post[]) {
  const byRecord = new Map(posts.filter((post) => !post.is_demo && postDay(post) === run.date).map((post) => [recordKey(post), post]))
  const sample = !run.daily_v2 && edition && run.run_id === edition.runId &&
    edition.signals.every((signal) => signal.evidence.every((id) => run.evidence[id])) ? edition : null
  const v2 = run.daily_v2
  const signals: SignalPreview[] = v2 ? v2.top_signals.map((item) => ({
    title: item.title, context: item.what_happened, support: item.bull_case,
    judgment: item.core_judgment ?? undefined, companyScope: item.company_scope ?? undefined,
    thesisStatus: item.thesis_status ?? undefined,
    evidence: [...new Set([...item.what_happened, ...item.bull_case])],
    why: item.why_it_matters, implication: item.investment_implication, risk: item.risks,
    action: [item.next_research_action], counter: item.bear_case, reason: item.selection_reason,
    tags: item.related_sectors, status: item.verification_status,
    companies: item.related_tickers,
    criteria: { ...item.criteria, evidence_quality: item.evidence_quality },
    ...reviewedSignal(run.run_id, item.event_key),
  })) : sample ? sample.signals : run.brief.hypotheses.slice(0, 3).map((item) => ({
    title: item.statement, evidence: item.support_item_ids, action: item.questions, counter: item.counter_item_ids, tags: [],
  }))
  const themes: { title: string; tags: string[]; evidence: string[]; text: string;
    sourceCount?: number; history?: { date: string; new_source_count: number }; conflicts?: string[] }[] = v2 ? v2.research_themes.map((item) => ({
      title: item.title, tags: item.related_companies, evidence: item.item_ids, text: item.current_observation,
      sourceCount: item.source_count, history: item.history, conflicts: item.conflicting_item_ids,
    })) : sample ? sample.themes : run.brief.themes.map((item) => ({
    title: item.text, tags: [], evidence: item.item_ids, text: '',
  }))
  const sourceRecords = (ids: string[]) =>
    new Set(ids.flatMap((id) => run.evidence[id]?.citations.map((cite) => cite.record_id) ?? []))
  const selected = sourceRecords(signals.flatMap((signal) => [...signal.evidence, ...signal.counter]))
  const leadIds = v2?.lead_insight?.item_ids ?? run.brief.summary?.item_ids ?? []
  const updates = v2?.other_updates.flatMap((item) => {
    const post = byRecord.get(item.record_id)
    const evidence = run.evidence[item.item_id]
    return post && evidence
      ? [{ post, id: item.record_id, title: item.title, industry: item.industry, summary: evidence.text }]
      : []
  })

  return {
    sample, signals, sourceRecords, byRecord, leadIds,
    lead: v2?.lead_insight?.title ?? sample?.lead ?? run.brief.summary?.text,
    explanation: v2?.lead_insight?.explanation ?? sample?.explanation,
    leadTags: [...(v2?.lead_insight?.related_sectors ?? sample?.tags ?? []), ...(v2?.lead_insight?.related_tickers ?? [])],
    leadSources: sourceRecords(leadIds),
    themes: themes.map((theme) => ({
      ...theme,
      sourceCount: theme.sourceCount ?? new Set([...sourceRecords(theme.evidence)].map((id) => byRecord.get(id)?.post_id || id)).size,
    })),
    updates: updates ?? run.records.flatMap((record) => {
      const post = byRecord.get(record.record_id)
      if (!post || selected.has(record.record_id)) return []
      const example = sample && sourceRecords([sample.update.id]).has(record.record_id)
      return [{ post, id: record.record_id, title: example && sample ? sample.update.title : post.title ?? '存档第 ' + record.excel_row + ' 行',
        industry: example && sample ? sample.update.industry : post.industry,
        summary: example && sample ? run.evidence[sample.update.id].text : post.summary ?? post.content.trim() }]
    }),
  }
}
