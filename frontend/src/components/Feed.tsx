import type { ReactNode } from 'react'
import { ChevronDown, FileSearch, FilterX, Search, SlidersHorizontal } from 'lucide-react'
import type { Dashboard } from '../model'
import { countBy, evidenceLabels, feedSort, feedSortLabels, missingAccount, number, periodLabels, postDay, postSectors, postTickers, recordKey, relevanceLabels, searchPosts } from '../research'
import { Badge } from './ui/badge'
import { Button } from './ui/button'
import { ArchiveCard, authorLabel, type PostDetail } from './ArchiveCard'
import { FeedMasonry } from './FeedMasonry'
import { PostDrawer } from './PostDrawer'

export { authorLabel } from './ArchiveCard'

const definitions = {
  fact: '来源提出的可核实陈述，核实状态见解读。',
  opinion: '来源作者的主观判断或预期。',
  inference: '基于来源证据提出的研究解读。',
} as const

export function postLink(id: string, date?: string | null) {
  const params = new URLSearchParams({ post: id })
  if (date) params.set('date', date)
  return '#/feed?' + params.toString()
}

function SelectFilter({ name, label, children, value, onChange, disabled }: {
  name: string
  label: string
  children: ReactNode
  disabled?: boolean
  value: string
  onChange: (name: string, value: string) => void
}) {
  return (
    <label className="filter-field">
      <span>{label}</span>
      <select name={name} value={value} disabled={disabled} onChange={(event) => onChange(name, event.target.value)}>
        <option value="">{disabled ? '待分析' : '全部'}</option>
        {children}
      </select>
    </label>
  )
}

export function Feed({ data, filters, onFilter }: {
  data: Dashboard
  filters: URLSearchParams
  onFilter: (params: URLSearchParams) => void
}) {
  const posts = searchPosts(data.posts, filters)
  const sort = feedSort(filters.get('sort'))
  const selected = filters.get('post')
  const selectedPost = selected ? posts.find((post) => recordKey(post) === selected) : undefined
  const requestedDetail = filters.get('detail')
  const detail = requestedDetail === 'analysis' || requestedDetail === 'quote' ? requestedDetail : 'body'
  const active = ['q', 'author', 'industry', 'ticker', 'period', 'relevance'].some((key) => !!filters.get(key))
  const date = filters.get('date')
  const archival = data.mode === 'research'
  const currentPosts = date ? data.posts.filter((post) => postDay(post) === date) : data.posts
  const ids = new Map(data.posts.map((post) => [recordKey(post), post]))
  function clearFilters() {
    const next = new URLSearchParams()
    if (date) next.set('date', date)
    if (sort !== 'newest') next.set('sort', sort)
    onFilter(next)
  }

  function relatedLink(id: string) {
    const target = ids.get(id)
    return postLink(id, date && target ? postDay(target) : null)
  }
  const demoAuthors = [...new Map(data.posts.filter((post) => post.is_demo).map((post) => [post.author, authorLabel(post)]))]
  const realCoverage = new Set(currentPosts.filter((post) => !post.is_demo).map((post) => post.author.toLowerCase()))
  const industries = countBy(currentPosts.flatMap(postSectors))
  const tickers = countBy(currentPosts.flatMap(postTickers))
  const hasRelevance = currentPosts.some((post) => post.relevance)

  function setFilter(name: string, value: string) {
    const next = new URLSearchParams(filters)
    if (value) next.set(name, value)
    else next.delete(name)
    next.delete('post')
    next.delete('detail')
    onFilter(next)
  }

  function closePost() {
    const next = new URLSearchParams(filters)
    next.delete('post')
    next.delete('detail')
    onFilter(next)
  }

  function openPost(id: string, detail: PostDetail) {
    const next = new URLSearchParams(filters)
    next.set('post', id)
    if (detail !== 'body') next.set('detail', detail)
    else next.delete('detail')
    onFilter(next)
  }

  const filter = (name: string) => ({ name, value: filters.get(name) ?? '', onChange: setFilter })

  return (
    <div className="feed-grid">
      <section className="panel filter-panel" aria-labelledby="filters-heading">
        <div className="panel-heading"><div><h2 id="filters-heading"><SlidersHorizontal size={17} aria-hidden="true" />搜索与筛选</h2></div>
          {active && <Button className="button--quiet" onClick={clearFilters}><FilterX size={15} aria-hidden="true" />清除筛选</Button>}
        </div>
        <label className="search-field">
          <Search size={18} aria-hidden="true" /><span className="sr-only">关键词搜索</span>
          <input id="archive-search" type="search" name="q" placeholder="搜索关键词、股票代码或账号…" autoComplete="off" spellCheck={false}
            value={filters.get('q') ?? ''} onChange={(event) => setFilter('q', event.target.value)} />
        </label>
        <div className="filter-grid">
          <SelectFilter {...filter('author')} label="账号">
            {demoAuthors.length > 0 && <optgroup label="合成样本">
              {demoAuthors.map(([id, label]) => <option key={id} value={id}>{label}</option>)}
            </optgroup>}
            <optgroup label="监控账号">
              {data.accounts.map(({ handle }) => <option key={handle} value={handle}>@{handle}{realCoverage.has(handle.toLowerCase()) ? '' : '（暂无样本）'}</option>)}
              {archival && realCoverage.has('') && <option value={missingAccount}>监控账号未记录</option>}
            </optgroup>
          </SelectFilter>
          <SelectFilter {...filter('industry')} label="行业" disabled={archival && !industries.length}>{industries.map(([label]) => <option key={label}>{label}</option>)}</SelectFilter>
          <SelectFilter {...filter('ticker')} label="股票代码" disabled={archival && !tickers.length}>{tickers.map(([label]) => <option key={label}>{label}</option>)}</SelectFilter>
          {!archival && <SelectFilter {...filter('period')} label="时间">{Object.entries(periodLabels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</SelectFilter>}
          <SelectFilter {...filter('relevance')} label="研究相关性" disabled={archival && !hasRelevance}>{Object.entries(relevanceLabels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</SelectFilter>
        </div>
      </section>
      <section aria-labelledby="results-heading">
        <div className="results-header">
          <div className="feed-results-heading">
            <h2 id="results-heading">情报列表</h2>
            <select className="feed-sort" aria-label="情报排序" value={sort}
              onChange={(event) => setFilter('sort', event.target.value === 'newest' ? '' : event.target.value)}>
              {Object.entries(feedSortLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </div>
          <div className="feed-results-tools">
            <span role="status">{number.format(posts.length)} 条结果</span>
            <details className="feed-legend">
              <summary>证据标记 <ChevronDown size={14} aria-hidden="true" /></summary>
              <div className="panel feed-legend-body">
                {Object.entries(definitions).map(([category, definition]) => {
                  const level = category as keyof typeof definitions
                  return <div className="legend-row" key={level}><Badge tone={level}><span className="badge-dot" />{level === 'fact' ? '事实性陈述' : evidenceLabels[level]}</Badge><p>{definition}</p></div>
                })}
              </div>
            </details>
          </div>
        </div>
        {posts.length === 0 ? (
          <div className="panel empty">
            <FileSearch size={26} aria-hidden="true" /><h3>暂无符合条件的资料</h3>
            <p>{filters.get('author') && !realCoverage.has(filters.get('author')!.toLowerCase()) && filters.get('author') !== missingAccount && !demoAuthors.some(([id]) => id === filters.get('author'))
              ? '该监控账号暂无真实样本。' : '试试调整关键词或筛选条件。'}</p>
            {active && <Button onClick={clearFilters}>清除筛选</Button>}
          </div>
        ) : <FeedMasonry>
          {posts.map((post) => <ArchiveCard key={recordKey(post)} post={post}
            onOpen={(detail) => openPost(recordKey(post), detail)} />)}
        </FeedMasonry>}
      </section>
      <PostDrawer post={selectedPost} detail={detail} onDismiss={closePost}
        onSelect={(view) => { if (selectedPost) openPost(recordKey(selectedPost), view) }}
        relations={data.relations ?? []} href={relatedLink} />
    </div>
  )
}
