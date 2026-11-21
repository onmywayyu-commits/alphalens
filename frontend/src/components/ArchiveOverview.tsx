import { ArrowRight, CalendarDays, FileCheck2, ImageIcon, Radio, ScanLine, Users } from 'lucide-react'
import type { Dashboard } from '../model'
import { archiveStats, missingAccount, number } from '../research'

export function ArchiveOverview({ data, date }: { data: Dashboard; date: string | null }) {
  const view = archiveStats(data, date)
  const start = view.dates[0]
  const end = view.dates.at(-1)
  const show = number.format
  const analyzedPercent = view.posts.length ? Math.round(100 * view.analyzed / view.posts.length) : 0
  const metrics = [
    { label: '监控账号', value: show(data.accounts.length), detail: `${show(view.covered)} 个账号有样本`, icon: Users },
    { label: '有效存档', value: show(view.posts.length), detail: `${show(view.postIds)} 个不同的 X 帖子 ID`, icon: Radio },
    { label: '具体原帖链接', value: `${show(view.sourceRows)} / ${show(view.posts.length)}`, detail: `${show(view.verified)} 条独立核验`, icon: FileCheck2 },
    { label: '可预览图片', value: show(view.availableImages), detail: `${show(view.attachments)} 个图片关联`, icon: ImageIcon },
  ]
  function feedLink(author?: string) {
    const params = new URLSearchParams()
    if (date) params.set('date', date)
    if (author) params.set('author', author)
    return params.size ? `#/feed?${params}` : '#/feed'
  }
  return (
    <div className="overview archive-overview">
      <section className="metrics" aria-label="采集概况" aria-live="polite">
        {metrics.map(({ label, value, detail, icon: Icon }) => (
          <div className="metric" key={label}>
            <div><span className="metric-icon"><Icon size={19} aria-hidden="true" /></span><span>{label}</span></div>
            <strong>{value}</strong><small>{detail}</small>
          </div>
        ))}
      </section>
      <div className="content-grid">
        <section className="panel" aria-labelledby="archive-coverage">
          <div className="panel-heading">
            <div><h2 id="archive-coverage"><Users size={17} aria-hidden="true" />监控账号覆盖</h2><p>{date ?? '全部存档'}，按 Excel 中记录的监控账号统计</p></div>
            <a className="text-link" href={feedLink()}>打开情报信息流 <ArrowRight size={15} aria-hidden="true" /></a>
          </div>
          <table className="coverage-table" aria-labelledby="archive-coverage">
            <thead><tr><th scope="col">监控账号</th><th scope="col">样本数</th></tr></thead>
            <tbody>
              {data.accounts.map(({ handle }) => (
                <tr key={handle}>
                  <th scope="row"><a href={feedLink(handle)} translate="no">@{handle}</a></th>
                  <td>{show(view.accountCounts.get(handle.toLowerCase()) ?? 0)} 条</td>
                </tr>
              ))}
              {view.unassigned > 0 && <tr><th scope="row"><a href={feedLink(missingAccount)}>未记录监控账号</a></th><td>{show(view.unassigned)} 条</td></tr>}
            </tbody>
          </table>
        </section>
        <div className="column">
          <section className="panel" aria-labelledby="archive-window">
            <div className="panel-heading"><div><h2 id="archive-window"><CalendarDays size={17} aria-hidden="true" />存档日期范围</h2></div></div>
            {start ? <p className="archive-range">
              <time dateTime={start}>{start}</time>{end && end !== start && <><span>至</span><time dateTime={end}>{end}</time></>}
            </p> : <p className="archive-status-copy">暂无存档日期</p>}
          </section>
          <section className="panel" aria-labelledby="archive-analysis">
            <div className="panel-heading"><div><h2 id="archive-analysis"><ScanLine size={17} aria-hidden="true" />分析进度</h2></div></div>
            <p className="archive-status-copy">已分析 {show(view.analyzed)} 条 <span>待分析 {show(view.posts.length - view.analyzed)} 条</span></p>
            <div className="archive-progress">
              <progress aria-label="分析进度" value={view.analyzed} max={view.posts.length || 1} />
              <span aria-hidden="true">{analyzedPercent}%</span>
            </div>
          </section>
        </div>
      </div>
    </div>
  )
}

