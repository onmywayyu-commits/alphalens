import { Activity, ArrowDownRight, ArrowRight, Building2, FileText, Radio, Radar, SignalHigh, Users } from 'lucide-react'
import type { Dashboard } from '../model'
import { formatTime, getOverview, number, recordKey } from '../research'
import { authorLabel, postLink } from './Feed'
import { Badge } from './ui/badge'

export function Overview({ data }: { data: Dashboard }) {
  const view = getOverview(data)
  const demo = data.mode === 'demo'
  const metrics = [
    { label: '监控账号', value: data.accounts.length, note: `${number.format(view.coverage.size)} 个已有真实样本`, icon: Users },
    { label: demo ? '合成样本' : '已处理帖子', value: view.posts.length, note: `${number.format(view.realCount)} 条真实帖子`, icon: Radio },
    { label: '高相关信号', value: view.highCount, note: demo ? '根据演示样本相关性统计' : '根据帖子相关性统计', icon: SignalHigh },
    { label: '研究假设', value: data.ideas.length, note: demo ? '演示卡片' : '线索雷达收录', icon: Radar },
  ]
  const covered = view.coverage.size

  return (
    <div className="overview">
      <section className="metrics" aria-label="研究概况">
        {metrics.map(({ label, value, note, icon: Icon }) => (
          <div className="metric" key={label}>
            <div><span>{label}</span><Icon size={18} aria-hidden="true" /></div>
            <strong>{number.format(value)}</strong><small>{note}</small>
          </div>
        ))}
      </section>
      <div className="content-grid">
        <div className="column">
          <section className="panel" aria-labelledby="themes-heading">
            <div className="panel-heading">
              <div><h2 id="themes-heading"><Activity size={18} aria-hidden="true" />重点行业主题</h2><p>{view.newestDay ? `${view.newestDay} 样本日 · 按帖子计数` : '暂无样本日'}</p></div>
              <a className="text-link" href="#/feed?period=newest">查看情报 <ArrowRight size={15} aria-hidden="true" /></a>
            </div>
            {view.themes.length ? <div className="theme-chart">
              {view.themes.map(([theme, count]) => (
                <a key={theme} href={`#/feed?period=newest&industry=${encodeURIComponent(theme)}`} className="theme-row">
                  <span>{theme}</span><span className="bar-track" aria-hidden="true"><span style={{ width: `${count / view.themes[0][1] * 100}%` }} /></span>
                  <strong>{number.format(count)} 条</strong>
                </a>
              ))}
            </div> : <p className="panel-empty">暂无行业主题。</p>}
          </section>
          <section className="panel" aria-labelledby="signals-heading">
            <div className="panel-heading"><div><h2 id="signals-heading"><Radio size={18} aria-hidden="true" />最新高相关信号</h2></div>
              <a className="text-link" href="#/feed?relevance=high">查看全部 <ArrowRight size={15} aria-hidden="true" /></a>
            </div>
            {view.highCount ? <div className="signal-list">
              {view.posts.filter((post) => post.relevance === 'high').slice(0, 3).map((post) => (
                <a className="signal-row" key={recordKey(post)} href={postLink(recordKey(post))}>
                  <div><strong>{post.title}</strong><small>{authorLabel(post)}{post.published_at && <span>{formatTime(post.published_at)}</span>}</small></div>
                  <ArrowDownRight size={16} aria-hidden="true" />
                </a>
              ))}
            </div> : <p className="panel-empty">暂无高相关信号。</p>}
          </section>
          <section className="panel" aria-labelledby="coverage-heading">
            <div className="panel-heading"><div><h2 id="coverage-heading"><Users size={17} aria-hidden="true" />监控账号覆盖</h2><p>X 公开账号 · {number.format(covered)} / {number.format(data.accounts.length)} 有真实样本</p></div></div>
            {data.accounts.length ? <div className="account-grid">
              {data.accounts.map(({ handle }) => (
                <a key={handle} href={`#/feed?author=${encodeURIComponent(handle)}`}><span translate="no">@{handle}</span>
                  <small>{view.coverage.get(handle) ? `${number.format(view.coverage.get(handle)!)} 条` : '暂无样本'}</small>
                </a>
              ))}
            </div> : <p className="panel-empty">暂无配置的监控账号。</p>}
          </section>
        </div>
        <div className="column">
          <section className="panel lead-panel" aria-labelledby="idea-heading">
            <div className="panel-heading"><div><h2 id="idea-heading"><Radar size={18} aria-hidden="true" />优先验证</h2></div></div>
            {data.ideas.length ? data.ideas.slice(0, 2).map((idea) => (
              <a className="compact-row" href={`#/ideas?idea=${encodeURIComponent(idea.id)}`} key={idea.id}>
                <div><strong>{idea.title}</strong><span>{idea.status}　{idea.tickers.join(' · ')}</span></div><ArrowRight size={15} aria-hidden="true" />
              </a>
            )) : <p className="panel-empty">暂无研究假设。</p>}
          </section>
          <section className="panel" aria-labelledby="companies-heading">
            <div className="panel-heading"><div><h2 id="companies-heading"><Building2 size={18} aria-hidden="true" />关联上市公司</h2><p>按样本提及次数排列</p></div></div>
            {view.tickers.length ? <div className="company-list">
              {view.tickers.slice(0, 5).map(([ticker, count]) => (
                <a key={ticker} href={`#/feed?ticker=${encodeURIComponent(ticker)}`}><span className="ticker" translate="no">{ticker}</span>
                  <span>{view.companies.get(ticker)?.name}</span><small>{number.format(count)} 次</small></a>
              ))}
            </div> : <p className="panel-empty">暂无关联公司。</p>}
          </section>
          <section className="panel report-preview" aria-labelledby="brief-heading">
            <div className="panel-heading"><div><h2 id="brief-heading"><FileText size={17} aria-hidden="true" />最新投研简报</h2></div>
              {view.report?.is_demo && <Badge tone="demo">演示</Badge>}
            </div>
            {view.report ? <div className="report-preview-content">
              <time dateTime={view.report.date}>{view.report.date}</time>
              <p>{view.report.summary}</p>
              <a className="text-link" href="#/reports">阅读简报 <ArrowRight size={15} aria-hidden="true" /></a>
            </div> : <p className="panel-empty">暂无已收录简报。</p>}
          </section>
        </div>
      </div>
    </div>
  )
}
