import type { Dashboard, Post } from './model.ts'

export const relevanceLabels = { high: '高相关', medium: '中相关', low: '低相关' } as const
export const evidenceLabels = { fact: '事实', opinion: '观点', inference: 'AI 推断' } as const
export const periodLabels = { newest: '最新样本日', week: '最近 7 个样本自然日' } as const
export const feedSortLabels = {
  oldest: '时间正序', newest: '时间倒序', account: '首字母正序（A–Z）', 'account-desc': '首字母倒序（Z–A）',
} as const
export const feedSort = (value: string | null) =>
  value === 'oldest' || value === 'account' || value === 'account-desc' ? value : 'newest'
export const missingAccount = ':unassigned'

export function xPostLink(value?: string | null) {
  return value && /^https:\/\/(?:www\.)?(?:x\.com|twitter\.com)\/(?:[A-Za-z0-9_]+|i\/web|i)\/status\/\d+\/?(?:[?#][^\s]*)?$/i.test(value)
    ? value : null
}

export const number = new Intl.NumberFormat('zh-CN')
const dateTime = new Intl.DateTimeFormat('zh-CN', {
  timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit',
  hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
})
const day = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit',
})

export const formatTime = (value: string) => dateTime.format(new Date(value))
export const shanghaiDay = (value: string) => day.format(new Date(value))
export const recordKey = (post: Post) => post.archive?.record_id ?? post.post_id ?? ''
export const postDay = (post: Post) =>
  post.archive ? post.archive.posted_date : post.published_at ? shanghaiDay(post.published_at) : null

function comparePostDates(a: Post, b: Post, direction: 1 | -1) {
  const aDay = postDay(a)
  const bDay = postDay(b)
  if (aDay !== bDay) {
    if (!aDay || !bDay) return aDay ? -1 : 1
    return direction * aDay.localeCompare(bDay)
  }
  return a.published_at && b.published_at ? direction * (Date.parse(a.published_at) - Date.parse(b.published_at)) : 0
}

export const newestFirst = (posts: readonly Post[]) => [...posts].sort((a, b) => comparePostDates(a, b, -1))

const accountCollator = new Intl.Collator('en', { sensitivity: 'base' })
const accountName = (post: Post) => (post.archive?.source_author_handle || post.author).trim().replace(/^@/, '')

export function countBy(values: readonly string[]) {
  const counts = new Map<string, number>()
  for (const value of values) counts.set(value, (counts.get(value) ?? 0) + 1)
  return [...counts].sort(([a, aCount], [b, bCount]) => bCount - aCount || a.localeCompare(b, 'zh-CN'))
}

export function archiveDates(data: Dashboard) {
  const dates = data.posts.flatMap((post) => post.archive?.posted_date ? [post.archive.posted_date] : [])
  return [...new Set([...dates, ...data.reports.map(({ date }) => date)])].sort().reverse()
}

export function archiveStats(data: Dashboard, date?: string | null) {
  const posts = data.posts.filter((post) => post.archive && (!date || postDay(post) === date))
  const accountCounts = new Map(countBy(posts.flatMap((post) => post.author ? [post.author.toLowerCase()] : [])))
  const monitored = new Set(data.accounts.map(({ handle }) => handle.toLowerCase()))
  const media = posts.flatMap((post) => post.archive?.media ?? [])
  const dates = [...new Set(posts.flatMap((post) => post.archive?.posted_date ? [post.archive.posted_date] : []))].sort()
  const analyzed = posts.filter((post) => post.archive?.analysis_status === 'analyzed').length

  return {
    posts, accountCounts, dates, analyzed,
    covered: [...accountCounts.keys()].filter((handle) => monitored.has(handle)).length,
    unassigned: posts.filter((post) => !post.author).length,
    sourceRows: posts.filter((post) => post.archive?.source_url_status === 'status').length,
    verified: posts.filter((post) => post.archive?.source_verification === 'verified').length,
    postIds: new Set(posts.flatMap((post) => post.post_id ? [post.post_id] : [])).size,
    attachments: media.length,
    availableImages: media.filter((item) => item.preview_path !== null).length,
  }
}

export function getOverview(data: Dashboard) {
  const posts = newestFirst(data.posts)
  const newestDay = posts[0] ? postDay(posts[0]) : null
  const latestPosts = posts.filter((post) => postDay(post) === newestDay)

  return {
    posts, newestDay,
    highCount: posts.filter((post) => post.relevance === 'high').length,
    realCount: posts.filter((post) => !post.is_demo).length,
    themes: countBy(latestPosts.flatMap((post) => post.industry ? [post.industry] : [])),
    tickers: countBy(posts.flatMap((post) => [...new Set(post.companies.map(({ ticker }) => ticker))])),
    companies: new Map(posts.flatMap((post) => post.companies.map((company) => [company.ticker, company] as const))),
    coverage: new Map(countBy(posts.filter((post) => !post.is_demo && post.author).map((post) => post.author))),
    report: [...data.reports].sort((a, b) => b.date.localeCompare(a.date))[0],
  }
}

export function postSectors(post: Post) {
  return [...new Set([...(post.industry ? [post.industry] : []), ...(post.post_analysis?.analysis.related_sectors ?? [])])]
}

export function postTickers(post: Post) {
  return [...new Set([...post.companies.map(({ ticker }) => ticker), ...(post.post_analysis?.analysis.related_tickers ?? [])])]
}

export function searchPosts(posts: readonly Post[], filters: URLSearchParams) {
  const query = (filters.get('q') ?? '').trim().normalize('NFKC').toLowerCase()
  const author = filters.get('author')?.toLowerCase()
  const industry = filters.get('industry')
  const ticker = filters.get('ticker')
  const relevance = filters.get('relevance')
  const period = filters.get('period')
  const date = filters.get('date')
  const ordered = newestFirst(posts)
  const latestDay = ordered[0] ? postDay(ordered[0]) : null
  const cutoff = Date.parse(latestDay ?? '') - 6 * 86_400_000

  const matches = ordered.filter((post) => {
    if ((author && (post.author.toLowerCase() || missingAccount) !== author) ||
        (industry && !postSectors(post).includes(industry)) ||
        (ticker && !postTickers(post).includes(ticker)) ||
        (relevance && post.relevance !== relevance)) return false
    const currentDay = postDay(post)
    if ((date && date !== currentDay) ||
        (period === 'newest' && currentDay !== latestDay) ||
        (period === 'week' && (!currentDay || Date.parse(currentDay) < cutoff))) return false
    const corpus = [
      post.title, post.author, post.post_id, post.summary, post.content, post.industry, post.information_type,
      post.archive?.author_display_name, post.archive?.source_author_handle,
      post.archive && post.author ? '@' + post.author : null,
      post.archive?.quoted_author_handle, post.archive?.quoted_content,
      ...post.companies.flatMap(({ ticker, name }) => [ticker, name]),
      ...post.evidence.map(({ text }) => text),
    ].join(' ').normalize('NFKC').toLowerCase()
    return query.split(/\s+/).every((term) => corpus.includes(term))
  })

  const sort = feedSort(filters.get('sort'))
  if (sort === 'oldest') return matches.sort((a, b) => comparePostDates(a, b, 1))
  if (sort === 'account' || sort === 'account-desc') {
    const direction = sort === 'account' ? 1 : -1
    return matches.sort((a, b) => {
      const left = accountName(a)
      const right = accountName(b)
      if (!left || !right) return Number(!left) - Number(!right)
      return direction * accountCollator.compare(left, right)
    })
  }
  return matches
}

export function archiveImageUrl(path: string | null, base: string) {
  return path && /^data\/archive-media\/[a-f0-9]{64}\.(?:jpg|png|webp)$/.test(path)
    ? new URL(path, base).href : null
}

