import { useEffect, useRef } from 'react'
import { ArrowRight, ArrowUpRight, ClipboardCheck, Focus, Search } from 'lucide-react'
import type { Dashboard } from '../model'
import { filterRadar, radarTheses, type RadarEvidenceGroup } from '../radar'
import { recordKey, xPostLink } from '../research'
import { authorLabel, postLink } from './Feed'
import { Badge } from './ui/badge'
import { Button } from './ui/button'

type Thesis = ReturnType<typeof radarTheses>[number]
const categories = { fact: '来源陈述', opinion: '作者观点', inference: '研究推断' } as const
const entries = { initial: '建立假设', follow_up: '后续资料 · 假设不变', context: '新增观点 · 假设不变' }

function EvidenceGroup({ group, data, date, support, counter, statements }: {
  group: RadarEvidenceGroup; data: Dashboard; date: string; support: string[]; counter: string[]; statements?: Record<string, string>
}) {
  return <div className="radar-source">
    {group.length > 1 && <p className="radar-source-group">同一来源组 · {group.length} 条存档</p>}
    {group.map((record) => {
      const post = data.posts.find((item) => recordKey(item) === record.recordId)
      const citations = record.items.flatMap(({ citations }) => citations)
      const original = new Map(citations.map((cite) => {
        const quoted = cite.kind === 'quote'
        const url = xPostLink(cite.source_url ?? (quoted ? post?.archive?.quoted_url : post?.source_url))
        return [url ?? (quoted ? 'quote' : 'post'), { url, quoted, status: cite.source_verification }] as const
      }))
      return <div className="radar-record" key={record.recordId}>
        <div className="radar-source-meta">
          <a className="text-link" href={postLink(record.recordId, date)}>{post ? authorLabel(post) + ' · ' : ''}存档第 {record.excelRow} 行</a>
          {[...original].map(([key, source]) => <span key={key}>
            {source.url && <a className="text-link" href={source.url} target="_blank" rel="noreferrer">{source.quoted ? '被引用帖' : 'X 原帖'} <ArrowUpRight size={12} aria-hidden="true" /></a>}
            <small>{source.status === 'verified' ? '出处已核验' : '出处待核实'}</small>
          </span>)}
        </div>
        {record.items.map(({ item, id, citations: refs }) => <div className="radar-evidence-item" key={id}>
          <Badge tone={item.category}>{categories[item.category]}</Badge>
          {counter.includes(id) ? <span className="radar-evidence-role">反方材料</span> : support.includes(id) && <span className="radar-evidence-role">支持线索</span>}
          <p>{statements?.[id] ?? item.text}</p>
          {[...new Set(refs.flatMap(({ excerpt }) => excerpt ? [excerpt] : []))].map((excerpt) => <blockquote key={excerpt}>{excerpt}</blockquote>)}
        </div>)}
      </div>
    })}
  </div>
}

export function ResearchRadar({ data, filters, onFilter }: {
  data: Dashboard; filters: URLSearchParams; onFilter: (params: URLSearchParams) => void
}) {
  const all = radarTheses(data)
  const query = filters.get('q') ?? ''
  const topic = filters.get('topic') ?? ''
  const status = filters.get('status') ?? ''
  const view = filters.get('view')
  const date = filters.get('date')
  const dated = date ? all.filter((thesis) => thesis.timeline.some((entry) => entry.date === date)) : all
  const visible = filterRadar(dated, query, topic, status)
  const selected = visible.find((item) => item.id === filters.get('idea')) ?? visible[0]
  const verification = useRef<HTMLElement>(null)
  const timeline = useRef<HTMLElement>(null)
  const topics = [...new Set(all.map((item) => item.topic))]

  useEffect(() => {
    const target = view === 'verification' ? verification.current : view === 'timeline' ? timeline.current : null
    if (!target) return
    const frame = requestAnimationFrame(() => {
      target.focus({ preventScroll: true })
      target.scrollIntoView({ block: 'start' })
    })
    return () => cancelAnimationFrame(frame)
  }, [view, selected?.id])

  function filter(key: string, value: string) {
    const next = new URLSearchParams(filters)
    if (value) next.set(key, value)
    else next.delete(key)
    next.delete('view')
    onFilter(next)
  }

  function thesisHref(thesis: Thesis, section?: string) {
    const next = new URLSearchParams(filters)
    next.set('idea', thesis.id)
    if (section) next.set('view', section)
    else next.delete('view')
    return '#/ideas?' + next.toString()
  }

  if (!all.length) return <section className="panel empty"><h2>暂无可追踪的假设</h2><p>首版雷达从已收录的日报信号建立假设。</p>
    <a className="text-link" href="#/reports?view=signals">查看日报信号 <ArrowRight size={15} aria-hidden="true" /></a>
  </section>

  return <div className="radar-workbench">
    <div className="radar-filters panel">
      <label className="radar-query"><span>搜索假设</span>
        <span className="radar-search-box"><Search size={17} aria-hidden="true" />
          <input type="search" value={query} onChange={(event) => filter('q', event.target.value)} placeholder="主题、公司或股票代码" />
        </span>
      </label>
      <label className="filter-field"><span>主题</span>
        <select value={topic} onChange={(event) => filter('topic', event.target.value)}>
          <option value="">全部主题</option>{topics.map((name) => <option key={name}>{name}</option>)}
        </select>
      </label>
      <label className="filter-field"><span>假设状态</span>
        <select value={status} onChange={(event) => filter('status', event.target.value)}>
          <option value="">全部状态</option><option value="to_validate">待验证</option>
          <option value="strengthened">证据增强</option><option value="weakened">证据减弱</option><option value="invalidated">已被证伪</option>
        </select>
      </label>
    </div>
    <div className="radar-columns">
      <section className="panel radar-index" aria-label="追踪列表">
        <header><h2>追踪列表</h2><span aria-live="polite">{visible.length} / {dated.length} 条</span></header>
        {visible.length ? <ul>
          {visible.map((item) => <li key={item.id}><a href={thesisHref(item, view ?? undefined)} className="radar-index-item" aria-current={selected?.id === item.id ? 'true' : undefined}>
            <span><strong>{item.name}</strong><small>{item.topic}</small></span><Badge tone="demo">待验证</Badge>
          </a></li>)}
        </ul> : <div className="radar-empty">
          {date && !dated.length ? <>
            <p>所选日期没有假设证据。</p><Button onClick={() => filter('date', '')}>查看全部日期</Button>
          </> : <>
            <p>没有符合条件的假设。</p>
            <Button onClick={() => onFilter(new URLSearchParams(date ? { date } : {}))}>清除筛选</Button>
          </>}
        </div>}
      </section>
      {selected && <article className="panel radar-detail" key={selected.id} aria-labelledby="radar-thesis-title">
        <header className="radar-head">
          <div className="radar-head-meta"><Badge tone="demo">待验证</Badge><span>{selected.topic}</span><span>首次收录 <time dateTime={selected.date}>{selected.date}</time></span></div>
          <h2 id="radar-thesis-title">{selected.title}</h2>
          {selected.companyScope ? <dl className="daily-signal-companies radar-company-scope">
            {selected.companyScope.direct.length > 0 && <div><dt>原始信息直接涉及</dt><dd>{selected.companyScope.direct.join('、')}</dd></div>}
            {selected.companyScope.value_chain.length > 0 && <div><dt>产业链观察</dt><dd>{selected.companyScope.value_chain.join('、')}</dd></div>}
          </dl> : selected.related.length > 0 && <div className="radar-tags">{selected.related.map((name) => <Badge key={name}>{name}</Badge>)}</div>}
        </header>
        <section className="radar-hypothesis">
          <h3>核心假设</h3><p>{selected.thesis}</p>
        </section>
        <div className="radar-links">
          <a className="text-link" href={thesisHref(selected, 'verification')}><Focus size={15} aria-hidden="true" />跳到验证事项</a>
          <a className="text-link" href={thesisHref(selected, 'timeline')}>跳到证据时间线 <ArrowRight size={14} aria-hidden="true" /></a>
        </div>
        <section className="radar-verification" ref={verification} tabIndex={-1} aria-labelledby="radar-verification-title">
          <h3 id="radar-verification-title"><ClipboardCheck size={18} aria-hidden="true" />验证事项</h3>
          <p>{selected.action.join(' ')}</p>
          <dl className="radar-outcomes">
            <div><dt>什么会支持假设</dt><dd>{selected.support}</dd></div>
            <div><dt>什么会削弱假设</dt><dd>{selected.challenge}</dd></div>
          </dl>
        </section>
        <section className="radar-timeline" ref={timeline} tabIndex={-1} aria-labelledby="radar-timeline-title">
          <header><h3 id="radar-timeline-title">证据时间线</h3><small>最近更新 <time dateTime={selected.latestDate}>{selected.latestDate}</time></small></header>
          <p className="radar-caveat">{selected.caveat} 当前尚无足以更新假设状态的证据。</p>
          <ol>
            {selected.timeline.map((item) => <li className="radar-event" key={item.date + item.kind}>
              <div className="radar-event-head">
                <time dateTime={item.date}>{item.date}</time><strong>{entries[item.kind]}</strong>
                <a className="text-link" href={'#/reports?date=' + item.date + '&view=signals'}>查看当日简报 <ArrowUpRight size={13} aria-hidden="true" /></a>
              </div>
              {item.kind === 'context' && <p className="radar-caveat">这条观点讨论器件价值分配，尚未提供付费出货证据。</p>}
              <details>
                <summary>{item.groups.length} 组来源 · {item.groups.reduce((size, group) => size + group.length, 0)} 条存档</summary>
                {item.groups.map((group) => <EvidenceGroup key={group[0].recordId} group={group} data={data} date={item.date} support={item.support} counter={item.counter} statements={item.statements} />)}
              </details>
            </li>)}
          </ol>
        </section>
      </article>}
    </div>
  </div>
}
