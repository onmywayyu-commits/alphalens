import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { getOverview, searchPosts, shanghaiDay } from '../src/research.ts'

const data = JSON.parse(readFileSync(new URL('../../data/processed/dashboard.json', import.meta.url), 'utf8'))
const find = (query) => searchPosts(data.posts, new URLSearchParams(query))

test('合成样本不会归到监控账号，也不带虚构原文链接', () => {
  const handles = new Set(data.accounts.map(({ handle }) => handle))
  for (const post of data.posts) {
    assert.equal(post.is_demo, true)
    assert.equal(post.source_type, 'synthetic')
    assert.equal(post.source_url, null)
    assert(!handles.has(post.author))
    assert.deepEqual(post.evidence.map(({ category }) => category), ['fact', 'opinion', 'inference'])
    assert.equal(post.evidence[0].verification, 'unverified')
    assert.equal(post.evidence[2].verification, null)
  }
})

test('总览从数据计算样本、信号、主题和覆盖', () => {
  const view = getOverview(data)
  assert.equal(view.realCount, 0)
  assert.equal(view.coverage.size, 0)
  assert.equal(view.highCount, 2)
  assert.equal(view.newestDay, '2026-11-20')
  assert.deepEqual(view.themes, [['AI 基础设施', 2], ['光通信', 1]])
  assert.equal(getOverview({ ...data, posts: [] }).newestDay, null)
  assert.equal(shanghaiDay('2026-11-19T16:30:00Z'), '2026-11-20')
})

test('组合筛选、全角关键词、真实账号空态和最新样本日', () => {
  assert.deepEqual(find('q=ｎｖｄａ&relevance=high&period=newest').map(({ post_id }) => post_id), ['demo-001'])
  assert.deepEqual(find('ticker=VRT&industry=数据中心电力').map(({ post_id }) => post_id), ['demo-004'])
  assert.equal(find('author=SemiAnalysis_').length, 0)
  assert.equal(find('author=demo-scenario-1').length, 2)
  assert.equal(find('period=newest').length, 3)
  assert.deepEqual(find('q=平均售价 光模块').map(({ post_id }) => post_id), ['demo-002'])
})

test('七日筛选以最新样本日为基准，含边界当天', () => {
  const newer = { ...data.posts[0], post_id: 'newer', published_at: '2026-11-20T02:00:00Z' }
  const boundary = { ...newer, post_id: 'boundary', published_at: '2026-11-13T16:00:00Z' }
  const older = { ...newer, post_id: 'older', published_at: '2026-11-13T15:59:59Z' }
  assert.deepEqual(searchPosts([older, boundary, newer], new URLSearchParams('period=week')).map(({ post_id }) => post_id), ['newer', 'boundary'])
})

test('日期排序保留已知时刻和同日存档顺序，缺日期的记录始终最后', () => {
  const sample = data.posts[0]
  const early = { ...sample, post_id: 'early', published_at: '2026-11-20T02:00:00Z' }
  const late = { ...early, post_id: 'late', published_at: '2026-11-20T09:00:00Z' }
  const archive = { ...early, post_id: 'archive', published_at: null, archive: { posted_date: '2026-11-20' } }
  const missing = { ...early, post_id: 'missing', published_at: null }
  const older = { ...early, post_id: 'older', published_at: '2026-11-04T02:00:00Z' }
  const ids = (query) => searchPosts([early, late, archive, missing, older], new URLSearchParams(query)).map(({ post_id }) => post_id)
  assert.deepEqual(ids(''), ['late', 'early', 'archive', 'older', 'missing'])
  assert.deepEqual(ids('sort=oldest'), ['older', 'early', 'late', 'archive', 'missing'])
  assert.deepEqual(ids('sort=unknown'), ids(''))
  assert.deepEqual(ids('sort=oldest&period=week'), ['early', 'late', 'archive'])
})

test('账号按 X 用户名双向排序，同账号保持最新优先，缺账号放最后', () => {
  const sample = data.posts[0]
  const beta = { ...sample, post_id: 'beta', author: 'beta', published_at: '2026-11-21T02:00:00Z' }
  const newer = { ...sample, post_id: 'newer', author: 'monitor', published_at: null,
    archive: { source_author_handle: '@Alpha', posted_date: '2026-11-20' } }
  const older = { ...sample, post_id: 'older', author: 'alpha', published_at: '2026-11-19T02:00:00Z' }
  const missing = { ...beta, post_id: 'missing', author: '' }
  const ids = (query) => searchPosts([beta, older, missing, newer], new URLSearchParams(query)).map(({ post_id }) => post_id)
  assert.deepEqual(ids('sort=account'), ['newer', 'older', 'beta', 'missing'])
  assert.deepEqual(ids('sort=account-desc'), ['beta', 'newer', 'older', 'missing'])
  assert.deepEqual(ids('sort=account-desc&author=monitor'), ['newer'])
  assert.deepEqual(ids('sort=account&author=monitor'), ['newer'])
})

test('卡片、简报和推断均能引用现有样本 ID', () => {
  const ids = new Set(data.posts.map(({ post_id }) => post_id))
  for (const item of [...data.ideas, ...data.reports, ...data.posts.flatMap(({ evidence }) => evidence)]) {
    assert(item.source_post_ids.length)
    assert(item.source_post_ids.every((id) => ids.has(id)))
  }
})
