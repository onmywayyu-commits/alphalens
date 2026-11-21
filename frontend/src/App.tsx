import { useEffect, useState } from 'react'
import { Activity, ArrowRight, BellRing, Compass, FileText, Layers3, LayoutDashboard, Moon, Radio, Radar, ScanLine, Search, Sun } from 'lucide-react'
import { loadDashboard } from './data'
import type { Dashboard } from './model'
import { archiveDates, formatTime } from './research'
import { Button } from './components/ui/button'
import { BackToTop } from './components/BackToTop'
import { Feed } from './components/Feed'
import { Overview } from './components/Overview'
import { ArchiveOverview } from './components/ArchiveOverview'
import { Ideas, Reports } from './components/ResearchPages'
import { ResearchRadar } from './components/ResearchRadar'

const pages = {
  overview: { label: '投研总览', icon: LayoutDashboard, intro: '跟踪重点行业、关联公司与关键事件，沉淀研究线索，验证投资假设，持续追踪进展。' },
  feed: { label: '情报信息流', icon: Radio, intro: '按来源与研究主题筛选，核对原始陈述、作者观点和 AI 推断。' },
  ideas: { label: '投资假设跟踪', icon: Radar, intro: '追踪值得验证的投资假设，回看每次证据更新。' },
  reports: { label: 'AI 每日投研简报', icon: FileText, intro: '按日期查看重点信号、证据和待验证问题。' },
}
type Page = keyof typeof pages
const workflow = [
  { label: '信息', icon: Radio, route: '#/feed' },
  { label: '研究信号', icon: Activity, route: '#/reports?view=signals', demoRoute: '#/feed?relevance=high' },
  { label: '投资假设', icon: Compass, route: '#/ideas' },
  { label: '证据验证', icon: ScanLine, route: '#/ideas?view=verification', demoRoute: '#/ideas' },
  { label: '持续追踪', icon: BellRing, route: '#/ideas?view=timeline', demoRoute: '#/reports' },
]

function getLocation() {
  const [route, query] = window.location.hash.slice(1).replace(/^\//, '').split('?')
  const page = Object.hasOwn(pages, route) ? route as Page : 'overview'
  return { page, filters: new URLSearchParams(query) }
}

function skipToMain(event: React.MouseEvent<HTMLAnchorElement>) {
  event.preventDefault()
  const main = document.getElementById('main')
  main?.focus()
  main?.scrollIntoView()
}

export function App() {
  const [{ page, filters }, setLocation] = useState(getLocation)
  const [data, setData] = useState<Dashboard | null>(null)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  const [theme, setTheme] = useState(() => document.documentElement.dataset.theme === 'warm' ? 'warm' : 'dark')
  const themeAction = theme === 'warm' ? '切换到暗黑主题' : '切换到暖色主题'

  function toggleTheme() {
    const next = theme === 'warm' ? 'dark' : 'warm'
    document.documentElement.dataset.theme = next
    document.querySelector<HTMLMetaElement>('meta[name="theme-color"]')?.setAttribute('content', next === 'warm' ? '#D4A088' : '#0F172A')
    setTheme(next)
    try {
      localStorage.setItem('alphalens.theme', next)
    } catch {
      // The current selection still works when storage is unavailable.
    }
  }

  useEffect(() => {
    const onLocation = () => setLocation(getLocation())
    window.addEventListener('hashchange', onLocation)
    return () => window.removeEventListener('hashchange', onLocation)
  }, [])

  useEffect(() => {
    document.title = `${pages[page].label} ｜ AlphaLens`
    window.scrollTo(0, 0)
  }, [page])

  useEffect(() => {
    const controller = new AbortController()
    loadDashboard(controller.signal).then(setData).catch((reason: Error) => {
      if (!controller.signal.aborted) setError(reason.message || '情报数据暂时无法读取。')
    })
    return () => controller.abort()
  }, [attempt])

  const view = filters.get('view')
  const date = filters.get('date')
  useEffect(() => {
    if (page === 'feed' && view === 'search' && data) document.getElementById('archive-search')?.focus()
  }, [page, view, data])
  useEffect(() => {
    if (page !== 'reports' || view !== 'signals' || !data) return
    const frame = requestAnimationFrame(() => {
      const heading = document.getElementById('daily-signals-title')
      heading?.focus({ preventScroll: true })
      heading?.scrollIntoView({ block: 'start' })
    })
    return () => cancelAnimationFrame(frame)
  }, [page, view, date, data])

  const archival = data?.mode === 'research'
  const dates = data && archival ? archiveDates(data) : []
  const requestedDate = filters.get('date')
  const selectedDate = requestedDate && dates.includes(requestedDate) ? requestedDate : null
  const visibleFilters = new URLSearchParams(filters)
  if (archival && !selectedDate) visibleFilters.delete('date')

  function scopedHref(href: string) {
    if (!selectedDate) return href
    return href + (href.includes('?') ? '&' : '?') + 'date=' + encodeURIComponent(selectedDate)
  }

  function workflowHref(route: string, demoRoute?: string) {
    if (data?.mode === 'demo' && demoRoute) return scopedHref(demoRoute)
    if (page === 'ideas' && route.startsWith('#/ideas?view=')) {
      const params = new URLSearchParams(visibleFilters)
      params.set('view', route.split('=')[1])
      return '#/ideas?' + params.toString()
    }
    return scopedHref(route)
  }

  function updateFilters(params: URLSearchParams) {
    const query = params.toString()
    window.history.replaceState(null, '', '#/' + page + (query ? '?' + query : ''))
    setLocation(getLocation())
  }

  function selectDate(date: string) {
    const next = new URLSearchParams(visibleFilters)
    if (date) next.set('date', date)
    else next.delete('date')
    next.delete('post')
    next.delete('detail')
    next.delete('period')
    updateFilters(next)
  }

  function retry() {
    setError('')
    setAttempt((previous) => previous + 1)
  }

  const showsWorkflow = page !== 'reports'

  return (
    <div className="shell">
      <a className="skip-link" href="#main" onClick={skipToMain}>跳到主要内容</a>
      <header className="topbar">
        <div className="topbar-inner">
          <a className="brand" href={scopedHref('#/overview')}>
            <span className="brand-mark"><Layers3 size={21} strokeWidth={1.8} aria-hidden="true" /></span>
            <span className="brand-name"><strong translate="no">AlphaLens</strong><small>AI 投研情报终端</small></span>
          </a>
          <nav className="nav" aria-label="主导航">
            {(['overview', 'feed', 'reports', 'ideas'] as const).map((name) => {
              const { label, icon: Icon } = pages[name]
              return <a key={name} href={scopedHref('#/' + name)} aria-current={page === name ? 'page' : undefined}>
                <Icon size={17} aria-hidden="true" /><span>{name === 'reports' ? '每日投研简报' : label}</span>
              </a>
            })}
          </nav>
          <div className="topbar-meta">
            <a className="nav-search" href={scopedHref('#/feed?view=search')} onClick={(event) => {
              if (page !== 'feed' || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || !data) return
              event.preventDefault()
              document.getElementById('archive-search')?.focus()
            }} aria-label="存档搜索" title="存档搜索"><Search size={18} aria-hidden="true" /><span>存档搜索</span></a>
            <button className="theme-toggle" type="button" onClick={toggleTheme} aria-label={themeAction} title={themeAction}>
              {theme === 'warm' ? <Moon size={19} aria-hidden="true" /> : <Sun size={20} aria-hidden="true" />}
            </button>
          </div>
        </div>
      </header>
      <main id="main" tabIndex={-1} className={'main main--' + page + (showsWorkflow ? ' main--workflow' : '')}>
        <header className={'page-heading archive-page-heading' + (showsWorkflow ? ' workflow-page-heading' : '')}>
          <div>
            <h1>{pages[page].label}</h1>
            <p>{pages[page].intro}</p>
          </div>
          {showsWorkflow && <nav className="heading-workflow" aria-label="投研流程">
            {workflow.map(({ label, icon: Icon, route, demoRoute }, index) => (
              <div className="workflow-step" key={label}>
                <a href={workflowHref(route, demoRoute)}><span className="step-icon"><Icon size={17} aria-hidden="true" /></span><span>{label}</span></a>
                {index < workflow.length - 1 && <ArrowRight className="step-arrow" size={15} aria-hidden="true" />}
              </div>
            ))}
          </nav>}
          {archival &&
            <label className="filter-field archive-date-picker">
              <select name="date" aria-label="选择存档日期"
                value={selectedDate ?? ''} onChange={(event) => selectDate(event.target.value)}>
                <option value="">{page === 'reports' ? '最新可读简报' : '全部日期'}</option>
                {dates.map((date) => <option key={date} value={date}>{date}</option>)}
              </select>
            </label>}
        </header>
        {data?.mode === 'demo' && (
          <div className="notice"><span className="badge-dot" aria-hidden="true" /><p><strong>演示数据</strong>　所有情报、研究线索与简报均为合成样本，仅用于验收界面。</p></div>
        )}
        {error && <div className="panel empty" role="alert"><h2>数据加载失败</h2><p>{error} 请检查本地服务和数据文件。</p><Button onClick={retry}>重新加载</Button></div>}
        {!data && !error && <p className="panel empty" role="status">正在读取投研数据…</p>}
        {data && page === 'overview' && (archival ? <ArchiveOverview data={data} date={selectedDate} /> : <Overview data={data} />)}
        {data && page === 'feed' && <Feed data={data} filters={visibleFilters} onFilter={updateFilters} />}
        {data && page === 'ideas' && (archival
          ? <ResearchRadar data={data} filters={visibleFilters} onFilter={updateFilters} />
          : <Ideas data={data} selected={filters.get('idea')} />)}
        {data && page === 'reports' && <Reports data={data} date={archival ? selectedDate : filters.get('date')} />}
        <footer className="footer">
          <span translate="no">AlphaLens</span>
          {data?.updated_at && <time dateTime={data.updated_at}>更新时间 {formatTime(data.updated_at)}</time>}
          <span>{archival ? '手动存档' : '北京时间 · UTC+8'}</span>
        </footer>
      </main>
      <BackToTop focusTargetId="main" />
    </div>
  )
}
