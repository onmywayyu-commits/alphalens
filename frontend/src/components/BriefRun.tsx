import { ArrowUpRight, ChartNoAxesColumn, ChevronDown, Database, FileText, Layers3, ListChecks, Radio, ScanLine, Target } from 'lucide-react'
import type { Account, BriefRunData, Post } from '../model'
import { briefLayout, type SignalPreview } from '../brief-layout'
import { groupSignalEvidence } from '../signal-card'
import { formatTime, xPostLink } from '../research'
import { isRadarThesis } from '../radar'
import { authorLabel, postLink } from './Feed'
import { MediaGallery } from './MediaGallery'
import { Badge } from './ui/badge'

const categories = { fact: '事实性陈述', opinion: '作者观点', inference: 'AI 推断' }
const parts = { body: '正文', quote: '引用', image: '图片' }
const thesisStatusLabels = { to_validate: '待验证', strengthened: '证据增强', weakened: '证据减弱', invalidated: '已被证伪' }
const criteriaLabels: Record<string, string> = {
  investment_importance: '投资重要性', information_increment: '信息增量', research_value: '研究价值',
  evidence_quality: '证据质量', verifiability: '未来可验证性',
}

export function BriefRun({ run, posts, accounts }: { run: BriefRunData; posts: Post[]; accounts: Account[] }) {
  const layout = briefLayout(run, posts)
  const coverage = run.coverage
  const mode = run.mode === 'rehearsal' ? '离线流程演练' : run.mode === 'replay' ? '本地回复回放' :
    run.provider === 'openrouter-chat-completions' ? 'OpenRouter 文字分析' : 'OpenAI 生成'
  const accountNames = new Set([...layout.byRecord.values()].map((post) => post.author).filter(Boolean))
  const monitoredAccounts = new Set(accounts.map(({ handle }) => handle.toLowerCase()))
  const coveredAccounts = new Set<string>()
  for (const { record_id } of run.records) {
    const handle = layout.byRecord.get(record_id)?.author.toLowerCase()
    if (handle && monitoredAccounts.has(handle)) coveredAccounts.add(handle)
  }

  function evidence(ids: string[], media = false) {
    return <ul className="daily-evidence-list">
      {[...new Set(ids)].map((id) => {
        const item = run.evidence[id]
        if (!item) return null
        return <li key={id}>
          <div className="daily-evidence-text"><Badge tone={item.category}>{categories[item.category]}</Badge><p>{item.text}</p></div>
          {item.citations.map((cite, i) => {
            const post = layout.byRecord.get(cite.record_id)
            const href = xPostLink(cite.source_url ?? (cite.kind === 'quote' ? post?.archive?.quoted_url : post?.source_url))
            const image = media && cite.kind === 'image'
              ? post?.archive?.media.find((asset) => asset.media_id === cite.media_id && asset.preview_path) : undefined
            return <div className="daily-citation" key={cite.record_id + '-' + i}>
              {cite.excerpt && <blockquote>{cite.excerpt}</blockquote>}
              <div className="daily-source-links">
                <a className="text-link" href={postLink(cite.record_id, run.date)}>
                  {post ? authorLabel(post) + ' · ' : ''}{parts[cite.kind]} · 存档第 {cite.excel_row} 行
                </a>
                {href && <a className="text-link" href={href} target="_blank" rel="noreferrer">X 原帖 <ArrowUpRight size={13} aria-hidden="true" /></a>}
                <small>{cite.source_verification === 'verified' ? '来源已核验' : '来源待核实'}</small>
              </div>
              {image && <MediaGallery media={[image]} recordId={cite.record_id + '-' + id + '-' + i} />}
            </div>
          })}
        </li>
      })}
    </ul>
  }

  function tags(items: string[]) {
    return items.length ? <div className="daily-tags">{items.map((item) => <Badge key={item}>{item}</Badge>)}</div> : null
  }

  function citedStatements(ids: string[], edits?: SignalPreview['statements']) {
    return (['fact', 'opinion'] as const).flatMap((category) => {
      const items = [...new Set(ids)].filter((id) => run.evidence[id]?.category === category)
      if (!items.length) return []
      return [<div className="daily-statement" key={category}>
        <Badge tone={category}>{category === 'fact' ? '来源陈述' : '作者观点'}</Badge>
        {category === 'fact' && <small>陈述待独立核实</small>}
        {items.map((id) => <p key={id}>{edits?.[id] ?? run.evidence[id].text}</p>)}
      </div>]
    })
  }

  function signalEvidence(groups: ReturnType<typeof groupSignalEvidence>, signal: SignalPreview) {
    return <ul className="daily-evidence-list daily-signal-sources">
      {groups.map(({ recordId, excelRow, items }) => {
        const post = layout.byRecord.get(recordId)
        const citations = items.flatMap((entry) => entry.citations)
        const originals = new Map(citations.map((cite) => {
          const href = xPostLink(cite.source_url ?? (cite.kind === 'quote' ? post?.archive?.quoted_url : post?.source_url))
          const type = cite.kind === 'quote' ? 'quote' : 'body'
          return [type + (href ?? ''), { href, type, verification: cite.source_verification }] as const
        }))
        const imageIds = new Set(citations.flatMap((cite) => cite.kind === 'image' && cite.media_id ? [cite.media_id] : []))
        const media = post?.archive?.media.filter((asset) => imageIds.has(asset.media_id) && asset.preview_path) ?? []
        return <li key={recordId}>
          <div className="daily-source-links daily-signal-source-head">
            <a className="text-link" href={postLink(recordId, run.date)}>{post ? authorLabel(post) + ' · ' : ''}存档第 {excelRow} 行</a>
            {[...originals].map(([key, source]) => <span className="daily-source-origin" key={key}>
              {source.href ? <a className="text-link" href={source.href} target="_blank" rel="noreferrer">
                {source.type === 'quote' ? '被引用帖' : 'X 原帖'} <ArrowUpRight size={13} aria-hidden="true" />
              </a> : <small>{source.type === 'quote' ? '引用' : '正文'}无原帖链接</small>}
              <small>{source.verification === 'verified' ? '原帖出处已核验' : '出处待核实'}</small>
            </span>)}
          </div>
          {items.map(({ id, item, citations: refs }) => (
            <div key={id} className="daily-signal-source-item">
              <div className="daily-evidence-text">
                <Badge tone={item.category}>{item.category === 'fact' ? '来源陈述' : categories[item.category]}</Badge>
                {signal.counter.includes(id) && <Badge tone="opinion">反方证据</Badge>}
                {!signal.counter.includes(id) && signal.support?.includes(id) && <Badge>支持线索</Badge>}
                <p>{signal.statements?.[id] ?? item.text}</p>
              </div>
              {[...new Set(refs.flatMap((cite) => cite.excerpt ? [cite.excerpt] : []))].map((excerpt) =>
                <blockquote key={excerpt}>{excerpt}</blockquote>)}
            </div>
          ))}
          {media.length > 0 && <MediaGallery media={media} recordId={'signal-' + recordId + '-' + items[0].id} />}
        </li>
      })}
    </ul>
  }

  function updates(items: typeof layout.updates) {
    return <ul className="daily-updates">
      {items.map(({ post, id, title, industry, summary }) => <li key={id}>
        <div>
          <h3>{title}</h3>
          <div className="daily-update-meta"><span>{authorLabel(post)}</span><time dateTime={run.date}>{post.published_at ? formatTime(post.published_at) : run.date}</time>
            {industry && <Badge>{industry}</Badge>}</div>
          <p>{summary}</p>
        </div>
        <a className="text-link" href={postLink(id, run.date)}>查看存档 <ArrowUpRight size={15} aria-hidden="true" /></a>
      </li>)}
    </ul>
  }

  return (
    <article className="daily-brief" aria-label="投研简报">
      <section className="daily-lead" aria-labelledby="daily-lead-title">
        <div className="daily-lead-kicker">
          <div><Radio size={17} aria-hidden="true" /><span>今日核心观察</span></div>
        </div>
        <h2 id="daily-lead-title">{layout.lead ?? '本期暂无可展示的核心观察'}</h2>
        {layout.explanation && <p className="daily-lead-copy">{layout.explanation}</p>}
        {run.mode === 'rehearsal' && <p className="daily-lead-copy">已完成离线流程演练，等待研究分析。</p>}
        <div className="daily-lead-meta">
          <div className="daily-lead-context">
            {tags(layout.leadTags)}
            <time dateTime={run.date}>{run.date}</time>
          </div>
          <div className="daily-lead-provenance">
            <span>{coverage.record_count} 条存档 · {accountNames.size} 个采集账号</span>
            <span>{coverage.verified_source_count ? coverage.verified_source_count + ' 条来源已核验' : '暂无独立核验来源'}</span>
            <span>{mode}</span>
            {layout.sample && <Badge tone="demo">真实存档 · 编辑版式示例</Badge>}
          </div>
        </div>
        {layout.leadSources.size > 0 && <details className="daily-details daily-lead-evidence">
          <summary><span>查看核心观察的来源</span><ChevronDown size={15} aria-hidden="true" /></summary>
          {evidence(layout.leadIds)}
        </details>}
      </section>

      <section className="daily-section" aria-labelledby="daily-signals-title">
        <div className="daily-section-title"><ScanLine size={19} aria-hidden="true" /><h2 id="daily-signals-title" tabIndex={-1}>今日重点投资信号</h2></div>
        {layout.signals.length ? <ol className="daily-signal-list">
          {layout.signals.map((signal, index) => {
            const statements = citedStatements(signal.context ?? signal.evidence, signal.statements)
            const eventKey = run.daily_v2?.top_signals[index]?.event_key
            const groups = groupSignalEvidence(run.evidence, [...signal.evidence, ...signal.counter])
            const itemCount = new Set(groups.flatMap((group) => group.items.map(({ id }) => id))).size
            const sourceState = signal.status === 'records_verified' ? '原帖出处已核验'
              : signal.status === 'partially_verified' ? '部分出处已核验' : '出处待核实'
            return <li key={signal.title + index}>
              <article className="daily-signal">
                <header className="daily-signal-header">
                  {(layout.sample || run.daily_v2) && <div className="daily-signal-order" aria-hidden="true">{String(index + 1).padStart(2, '0')}</div>}
                  <div className="daily-signal-heading">
                    <h3>{signal.title}</h3>
                    {tags(signal.tags)}
                  </div>
                  {signal.status && <Badge tone={signal.status === 'records_verified' ? 'fact' : 'demo'}>{sourceState}</Badge>}
                </header>
                {signal.companyScope ? <dl className="daily-signal-companies">
                  {signal.companyScope.direct.length > 0 && <div><dt>原始信息直接涉及</dt><dd>{signal.companyScope.direct.join('、')}</dd></div>}
                  {signal.companyScope.value_chain.length > 0 && <div><dt>产业链延伸观察</dt><dd>{signal.companyScope.value_chain.join('、')}</dd></div>}
                </dl> : Boolean(signal.companies?.length) && <p className="daily-signal-reason">归档关注标的　{signal.companies?.join('、')}</p>}
                {signal.reason && <p className="daily-signal-reason"><strong>入选原因</strong>{signal.reason}</p>}
                {signal.judgment && <section className="daily-signal-judgment">
                  <h4><Target size={19} aria-hidden="true" />核心研究判断</h4>
                  <p>{signal.judgment}</p>
                </section>}
                <section className="daily-signal-group daily-signal-group--context">
                  <h4><Layers3 size={19} aria-hidden="true" />01 · 信息与影响</h4>
                  <div className="daily-signal-columns">
                    <section className="daily-signal-block">
                      <h5>发生了什么</h5>
                      {statements.length ? statements : <p>展开原始证据查看本条研究信号的依据。</p>}
                    </section>
                    <section className="daily-signal-block">
                      <h5>为什么重要</h5>
                      <p>{signal.why ?? '本期归档暂无独立的影响分析。'}</p>
                    </section>
                  </div>
                </section>
                <section className="daily-signal-group daily-signal-group--research">
                  <h4><ChartNoAxesColumn size={19} aria-hidden="true" />02 · 研究研判</h4>
                  <div className="daily-signal-columns">
                    <section className="daily-signal-block">
                      <h5>投资研究含义</h5>
                      <div className="daily-thesis-labels">
                        <Badge tone="inference">{layout.sample ? '编辑示例 · 研究推断' : 'AI 研究推断'}</Badge>
                        {signal.thesisStatus && <span>{thesisStatusLabels[signal.thesisStatus]}</span>}
                      </div>
                      <p>{signal.implication ?? signal.title}</p>
                    </section>
                    <section className="daily-signal-block">
                      <h5>风险与反方观点</h5>
                      {signal.risk && <p><strong>反方假设</strong>　{signal.risk}</p>}
                      <p className="daily-counter-note">{signal.counter.length ? '已有反方证据，见下方原始证据。' : '现有样本未提供独立反方证据。'}</p>
                    </section>
                  </div>
                </section>
                <section className="daily-next" aria-label="下一步验证">
                  <h4><ListChecks size={19} aria-hidden="true" />下一步验证</h4>
                  <div>{signal.action.map((action, i) => <p key={i}>{action}</p>)}</div>
                </section>
                <footer className="daily-signal-footer">
                  {eventKey && isRadarThesis(eventKey) && <a className="text-link daily-radar-link" href={'#/ideas?idea=' + encodeURIComponent(eventKey)}>
                    查看追踪假设 <ArrowUpRight size={14} aria-hidden="true" />
                  </a>}
                  <details className="daily-details daily-signal-evidence">
                    <summary><span>原始证据 <small>{groups.length} 条存档 · {itemCount} 项引用</small></span><ChevronDown size={17} aria-hidden="true" /></summary>
                    {signalEvidence(groups, signal)}
                    {signal.criteria && <details className="daily-details daily-original">
                      <summary><span>排序依据</span><ChevronDown size={15} aria-hidden="true" /></summary>
                      <ul>{Object.entries(signal.criteria).map(([key, value]) =>
                        <li key={key}><strong>{criteriaLabels[key]}</strong> {value.level}/2 · {value.reason}</li>)}</ul>
                    </details>}
                  </details>
                </footer>
              </article>
            </li>
          })}
        </ol> : <p className="daily-empty">本期暂无可展示的投资信号。</p>}
      </section>

      <section className="daily-section" aria-labelledby="daily-themes-title">
        <div className="daily-section-title"><h2 id="daily-themes-title">行业主题与变化</h2></div>
        {layout.themes.length ? <div className="daily-themes">
          {layout.themes.map((theme, index) => <article className="daily-theme" key={theme.title + index}>
            <div className="daily-theme-head"><h3>{theme.title}</h3><span>{theme.sourceCount} {run.daily_v2 ? '组存档来源' : '个存档来源'}</span></div>
            {tags(theme.tags)}
            {theme.text && <p>{theme.text}</p>}
            <small>{theme.history
              ? '与 ' + theme.history.date + ' 对照，新增 ' + theme.history.new_source_count + ' 组可定位来源。'
              : '历史证据不足，暂无法判断变化。'}</small>
            {theme.conflicts?.length ? <details className="daily-details">
              <summary><span>查看存在冲突的观点</span><ChevronDown size={15} aria-hidden="true" /></summary>
              {evidence(theme.conflicts)}
            </details> : <small>当前样本未收录可确认的观点冲突。</small>}
          </article>)}
        </div> : <p className="daily-empty">本期暂无行业主题。历史证据不足，暂无法判断变化。</p>}
      </section>

      <section className="daily-section" aria-labelledby="daily-updates-title">
        <div className="daily-section-title"><h2 id="daily-updates-title">其他值得关注的信息</h2></div>
        {layout.updates.length ? updates(layout.updates.slice(0, 4)) : <p className="daily-empty">本期没有其他可展示的更新。</p>}
        {layout.updates.length > 4 && <details className="daily-details">
          <summary><span>查看其余 {layout.updates.length - 4} 条更新</span><ChevronDown size={15} aria-hidden="true" /></summary>
          {updates(layout.updates.slice(4))}
        </details>}
      </section>

      <details className="daily-details daily-method">
        <summary><span><Database size={17} aria-hidden="true" />数据来源与系统能力</span><ChevronDown size={17} aria-hidden="true" /></summary>
        <div className="daily-method-body">
          <section className="daily-method-section">
            <div className="daily-method-heading">
              <h3>当前运行模式</h3><Badge tone="demo">Demo 模式</Badge>
            </div>
            <p>当前版本基于手动采集的历史 X 信息存档进行静态研究演示，非实时监控。</p>
            <p>本版本用于展示信息整理、研究信号提取、投资假设构建及投研简报呈现的完整流程。</p>
            <p className="daily-method-note">本期简报：{layout.sample ? '编辑版式示例' : run.mode === 'replay' ? '本地回放' : mode}</p>
          </section>

          <section className="daily-method-section">
            <h3>当前数据与研究流程</h3>
            <div className="daily-method-overview">
              <dl>
                <div><dt>本期有效存档</dt><dd>{coverage.record_count} 条</dd></div>
                <div><dt>有样本的监控账号</dt><dd>{coveredAccounts.size} 个</dd></div>
                <div><dt>数据覆盖日期</dt><dd><time dateTime={run.date}>{run.date}</time></dd></div>
              </dl>
              <div className="daily-method-workflow">
                <h4>研究处理流程</h4>
                <p>存档整理 → 信号提取 → 假设构建 → 简报呈现</p>
                <a className="text-link" href={'#/feed?date=' + encodeURIComponent(run.date)}><FileText size={15} aria-hidden="true" />查看当日存档</a>
              </div>
            </div>

            {((run.daily_v2?.limitations.length ?? 0) > 0 || Object.keys(run.evidence).length > 0) && <details className="daily-details daily-original">
              <summary><span>证据与研究局限</span><ChevronDown size={15} aria-hidden="true" /></summary>
              {run.daily_v2 && run.daily_v2.limitations.length > 0 && <section>
                <h4>数据与研究局限</h4><ul>{run.daily_v2.limitations.map((note) => <li key={note}>{note}</li>)}</ul>
              </section>}
              {Object.keys(run.evidence).length > 0 && <section><h4>完整证据引用</h4>{evidence(Object.keys(run.evidence))}</section>}
            </details>}

            {(run.brief.summary || run.brief.events.length + run.brief.themes.length + run.brief.questions.length + run.brief.risks.length + run.brief.hypotheses.length > 0) && (
              <details className="daily-details daily-original">
                <summary><span>查看原版归档分析</span><ChevronDown size={15} aria-hidden="true" /></summary>
                {([['原版摘要', run.brief.summary ? [run.brief.summary] : []], ['事件', run.brief.events], ['主题', run.brief.themes],
                  ['待验证问题', run.brief.questions], ['风险', run.brief.risks]] as const)
                  .filter(([, items]) => items.length).map(([title, items]) => <section key={title}><h4>{title}</h4>
                    {items.map((item, i) => <p key={i}>{item.text}</p>)}</section>)}
                {run.brief.hypotheses.length > 0 && <section><h4>原版投资假设</h4>
                  {run.brief.hypotheses.map((item) => <div key={item.comparison_key}>
                    <p>{item.statement}</p>
                    <ul>{item.questions.map((question, i) => <li key={i}>{question}</li>)}</ul>
                  </div>)}</section>}
              </details>
            )}
          </section>

          <section className="daily-method-section">
            <h3>后续扩展</h3>
            <p>系统采用模块化数据处理架构，后续可通过合规的 X API 或其他授权数据源实现增量采集，并接入 LLM 服务，支持自动投研解读、每日简报生成及投资研究观点的持续追踪。</p>
          </section>
        </div>
      </details>
    </article>
  )
}
