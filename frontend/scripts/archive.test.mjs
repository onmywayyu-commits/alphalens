import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import test from 'node:test'
import { archivePreview } from '../archive-preview.mjs'
import { archiveDates, archiveImageUrl, archiveStats, missingAccount, recordKey, searchPosts } from '../src/research.ts'

const basePost = {
  post_id: '123', author: 'Source', published_at: null, companies: [], evidence: [],
  content: '存档 正文', is_demo: false,
  archive: {
    record_id: 'archive-a', posted_date: '2026-11-20', analysis_status: 'not_analyzed',
    source_url_status: 'status', source_verification: 'pending', quoted_content: '引文关键字',
    media: [{ preview_path: 'data/archive-media/' + 'b'.repeat(64) + '.jpg' }],
  },
}
const second = { ...basePost, archive: { ...basePost.archive, record_id: 'archive-b', media: [] } }
const older = {
  ...basePost, post_id: '987', author: '', archive: {
    ...basePost.archive, record_id: 'archive-c', posted_date: '2026-11-04', media: [],
  },
}
const records = { accounts: [{ handle: 'Source' }], reports: [], posts: [basePost, second, older] }

test('按存档日期同步筛选与统计，并保留共用 X ID 的不同记录', () => {
  assert.deepEqual(archiveDates(records), ['2026-11-20', '2026-11-04'])
  assert.deepEqual(archiveStats(records, '2026-11-20').posts.map(recordKey), ['archive-a', 'archive-b'])
  assert.equal(archiveStats(records, '2026-11-20').postIds, 1)
  assert.equal(archiveStats(records, '2026-11-20').availableImages, 1)
  assert.equal(archiveStats(records, '2026-11-04').covered, 0)
  assert.equal(archiveStats(records, '2026-11-04').unassigned, 1)
  const matching = searchPosts(records.posts, new URLSearchParams({ date: '2026-11-20', author: 'source', q: '引文关键字 @Source' }))
  assert.deepEqual(matching.map(recordKey), ['archive-a', 'archive-b'])
  assert.deepEqual(searchPosts(records.posts, new URLSearchParams({ author: missingAccount })).map(recordKey), ['archive-c'])
})

test('预览图仅接受规范的相对路径', () => {
  const base = 'http://127.0.0.1:5175/'
  assert.equal(archiveImageUrl(basePost.archive.media[0].preview_path, base), base + basePost.archive.media[0].preview_path)
  for (const bad of ['https://example.com/a.jpg', 'data/archive-media/../a.jpg', 'C:\\folder\\a.jpg', null]) {
    assert.equal(archiveImageUrl(bad, base), null)
  }
})

function request(handler, url, { address = '127.0.0.1', host = '127.0.0.1:5175', site = 'same-origin', method = 'GET' } = {}) {
  return new Promise((resolve, reject) => {
    const headers = {}
    const response = {
      statusCode: 200,
      setHeader: (name, value) => { headers[name] = value },
      end: (body) => resolve({ status: response.statusCode, body, headers }),
    }
    handler({ url, method, socket: { remoteAddress: address }, headers: { host, 'sec-fetch-site': site } },
      response, (error) => error ? reject(error) : resolve({ status: 'next' }))
  })
}

const snapshot = new URL('../.local-archive/dashboard.json', import.meta.url)

test('本机预览提供真实快照与已关联图片，其他来源无法读取', { skip: !existsSync(snapshot) }, async () => {
  let handler
  archivePreview().configureServer({ middlewares: { use: (callback) => { handler = callback } } })
  const expected = JSON.parse(readFileSync(snapshot, 'utf8'))
  const response = await request(handler, '/data/dashboard.json')
  assert.equal(response.status, 200)
  assert.equal(response.headers['Cache-Control'], 'no-store')
  assert.deepEqual(JSON.parse(response.body), expected)
  const pictures = expected.posts.flatMap((post) => post.archive.media).filter((item) => item.preview_path)
  for (const picture of pictures) {
    const path = '/' + picture.preview_path
    const image = await request(handler, path)
    assert.equal(image.status, 200)
    assert.match(image.headers['Content-Type'], /^image\//)
    assert(image.body.length > 0)
    assert.equal((await request(handler, path, { method: 'HEAD' })).body, undefined)
    assert.equal((await request(handler, path, { site: 'cross-site' })).status, 404)
    assert.equal((await request(handler, path, { address: '192.0.2.10' })).status, 404)
  }
  assert.equal((await request(handler, '/data/dashboard.json', { host: 'example.com' })).status, 'next')
  assert.equal((await request(handler, '/data/archive-media/' + '0'.repeat(64) + '.jpg')).status, 404)
})

