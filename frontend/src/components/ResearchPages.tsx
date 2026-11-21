import { ArrowRight, CalendarDays, FileText, ListChecks } from 'lucide-react'
import type { Dashboard, Idea } from '../model'
import { authorLabel, postLink } from './Feed'
import { Badge } from './ui/badge'
import { BriefRun } from './BriefRun'
import { postDay, recordKey } from '../research'

function Sources({ data, ids }: { data: Dashboard; ids: string[] }) {
  const byId = new Map(data.posts.map((post) => [recordKey(post), post]))
  return (
    <section className="sources">
      <h3>证据来源</h3>
      {ids.length ? <ul>{ids.map((id) => {
        const post = byId.get(id)
        return <li key={id}>{post ? <a href={postLink(id, post.archive ? postDay(post) : null)}><span>{authorLabel(post)}　{post.title ?? (post.archive ? 'Excel 第 ' + post.archive.excel_row + ' 行' : '')}</span><ArrowRight size={15} aria-hidden="true" /></a>
          : <span>{id}（暂无可展示记录）</span>}</li>
      })}</ul> : <p>暂无证据记录。</p>}
    </section>
  )
}

function IdeaCard({ idea, data, active }: { idea: Idea; data: Dashboard; active: boolean }) {
  return (
    <article className={`panel research-card${active ? ' research-card--selected' : ''}`}>
      <div className="research-card-header">
        <div className="post-tags">
          <Badge>{idea.industry}</Badge><Badge tone="fact">{idea.status}</Badge>
          {idea.is_demo && <Badge tone="demo">演示线索</Badge>}
        </div>
        <h2>{idea.title}</h2>
        <div className="post-tags">{idea.tickers.map((ticker) => <a key={ticker} className="ticker" href={`#/feed?ticker=${encodeURIComponent(ticker)}`} translate="no">{ticker}</a>)}</div>
      </div>
      <section className="hypothesis"><h3>核心投资假设</h3><p>{idea.hypothesis}</p></section>
      <dl className="idea-factors">
        <div><dt>支持逻辑</dt><dd>{idea.supporting_logic}</dd></div>
        <div><dt>反方观点</dt><dd>{idea.counterargument}</dd></div>
        <div><dt>潜在催化剂</dt><dd>{idea.catalyst}</dd></div>
        <div><dt>风险与不确定性</dt><dd>{idea.risk}</dd></div>
      </dl>
      <section className="questions"><h3><ListChecks size={17} aria-hidden="true" />下一步验证问题</h3><ul>{idea.questions.map((question) => <li key={question}>{question}</li>)}</ul></section>
      <Sources data={data} ids={idea.source_post_ids} />
    </article>
  )
}

export function Ideas({ data, selected }: { data: Dashboard; selected: string | null }) {
  return data.ideas.length ? (
    <div className="ideas-grid">{data.ideas.map((idea) => <IdeaCard key={idea.id} idea={idea} data={data} active={idea.id === selected} />)}</div>
  ) : <section className="panel empty"><h2>暂无线索</h2><p>已有情报可在信息流查看。</p><a className="text-link" href="#/feed">打开情报信息流 <ArrowRight size={15} aria-hidden="true" /></a></section>
}

export function Reports({ data, date }: { data: Dashboard; date: string | null }) {
  const runs = data.brief_runs ?? []
  const run = date
    ? runs.find((item) => item.date === date)
    : runs.find((item) => item.mode !== 'rehearsal' && (item.daily_v2?.lead_insight || item.brief.summary || Object.keys(item.evidence).length)) ?? runs[0]
  if (data.mode === 'research' && run) return <BriefRun key={run.run_id} run={run} posts={data.posts} accounts={data.accounts} />

  const reports = [...data.reports].sort((a, b) => b.date.localeCompare(a.date))
  const report = reports.find((item) => item.date === date) ?? (date && data.mode === 'research' ? undefined : reports[0])

  if (!report) return <section className="panel empty"><h2>{date ? date + ' 的投研简报待生成' : '暂无投研简报'}</h2>
    <p>选中日期的存档可在情报信息流查看。</p>
    <a className="text-link" href={date ? '#/feed?date=' + encodeURIComponent(date) : '#/feed'}>查看存档 <ArrowRight size={15} aria-hidden="true" /></a>
  </section>

  const sections = [
    ['关键事件', report.events], ['行业主题变化', report.themes], ['新增投资假设', report.hypotheses],
    ['待验证问题', report.questions], ['风险提示', report.risks],
  ] as const

  return (
    <div className="content-grid reports-grid">
      <article className="panel research-card">
        <div className="report-title"><FileText size={22} aria-hidden="true" /><div>
          <h2><time dateTime={report.date}>{report.date}</time> 投研简报</h2>
          {report.is_demo && <Badge tone="demo">合成简报样例</Badge>}
        </div></div>
        <section className="hypothesis"><h3>简报摘要</h3><p>{report.summary}</p></section>
        <div className="report-sections">{sections.map(([label, values]) => (
          <section key={label}><h3>{label}</h3>{values.length ? <ul>{values.map((value) => <li key={value}>{value}</li>)}</ul> : <p>暂无记录。</p>}</section>
        ))}</div>
        <Sources data={data} ids={report.source_post_ids} />
      </article>
      <nav className="panel legend" aria-label="简报归档">
        <div className="panel-heading"><div><h2><CalendarDays size={17} aria-hidden="true" />简报归档</h2></div></div>
        {reports.map((item) => (
          <a className="compact-row archive-row" key={item.date} href={`#/reports?date=${item.date}`} aria-current={item.date === report.date ? 'date' : undefined}>
            <time dateTime={item.date}>{item.date}</time><ArrowRight size={15} aria-hidden="true" />
          </a>
        ))}
      </nav>
    </div>
  )
}
