import { createHash } from 'node:crypto'
import { copyFile, lstat, mkdir, readFile, readdir, unlink, writeFile } from 'node:fs/promises'

export const privateSnapshot = new URL('../.local-archive/pages-snapshot/', import.meta.url)
export const releaseSnapshot = new URL('../../data/public-snapshot/', import.meta.url)
const archive = new URL('../.local-archive/', import.meta.url)
const mediaPath = /^data\/archive-media\/([a-f0-9]{64})\.(?:jpg|png|webp)$/
const sensitiveText = /-----BEGIN [A-Z ]*PRIVATE KEY-----|\b(?:sk-(?:proj-|or-v1-)?[a-z0-9_-]{22,}|gh[pousr]_[a-z0-9]{25,}|github_pat_[a-z0-9_]{35,})|[a-z]:[\\/]+(?:Users|home|workspace)[\\/]|\/(?:home|Users)\/[a-z0-9_.-]+\//i

function checkDashboard(data) {
  if (data.schema_version !== 1 || data.mode !== 'research' ||
      !['accounts', 'posts', 'ideas', 'reports', 'brief_runs'].every((key) => Array.isArray(data[key])) ||
      !data.posts.length) {
    throw new Error('静态快照必须使用 research 模式并包含研究存档。')
  }

  const records = new Set()
  const media = new Set()
  for (const post of data.posts) {
    const item = post?.archive
    if (!item?.record_id || records.has(item.record_id) || post.is_demo !== false || !Array.isArray(item.media)) {
      throw new Error('研究快照包含无效或重复的归档记录。')
    }
    records.add(item.record_id)
    for (const { preview_path: path } of item.media) {
      if (path === null) continue
      if (typeof path !== 'string' || !mediaPath.test(path)) throw new Error('研究快照包含非法图片路径。')
      media.add(path)
    }
  }
  for (const run of data.brief_runs) {
    if (!Array.isArray(run.records) || run.records.some(({ record_id }) => !records.has(record_id))) {
      throw new Error('研究简报引用了缺失的归档记录。')
    }
  }
  return media
}

async function filesIn(dir, prefix = '') {
  if (!(await lstat(dir)).isDirectory()) throw new Error('静态快照必须存放在普通目录。')
  const files = []
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const path = prefix + entry.name
    if (entry.isSymbolicLink()) throw new Error('发布目录内不可包含符号链接。')
    if (entry.isDirectory()) {
      if (path !== 'data' && path !== 'data/archive-media') throw new Error('发布目录包含额外目录。')
      files.push(...await filesIn(new URL(entry.name + '/', dir), path + '/'))
    } else if (entry.isFile()) {
      files.push(path)
    } else {
      throw new Error('发布目录包含非普通文件。')
    }
  }
  return files
}

async function checkImage(url, path) {
  const stat = await lstat(url)
  if (!stat.isFile()) throw new Error('研究快照引用了非普通图片文件。')
  const digest = createHash('sha256').update(await readFile(url)).digest('hex')
  if (digest !== mediaPath.exec(path)[1]) throw new Error('研究快照的图片校验失败。')
}

export async function validateResearchSnapshot(root) {
  const dashboardPath = 'data/dashboard.json'
  let files
  try { files = await filesIn(root) }
  catch (error) {
    if (error.code === 'ENOENT') throw new Error('找不到静态研究快照。公开构建需要已审阅的 data/public-snapshot/。', { cause: error })
    throw error
  }
  if (!files.includes(dashboardPath)) throw new Error('静态研究快照缺少 data/dashboard.json。')
  const raw = await readFile(new URL(dashboardPath, root), 'utf8')
  if (sensitiveText.test(raw)) throw new Error('静态快照包含疑似密钥或本机路径，请人工核对。')
  const media = checkDashboard(JSON.parse(raw))
  if (files.length !== 1 + media.size || [...media].some((path) => !files.includes(path))) {
    throw new Error('静态快照包含未引用的文件或缺少已引用图片。')
  }
  await Promise.all([...media].map((path) => checkImage(new URL(path, root), path)))
}

export async function preparePrivateSnapshot({ withoutMedia }) {
  const data = JSON.parse(await readFile(new URL('dashboard.json', archive), 'utf8'))
  delete data.archive_workbook_sha256
  for (const post of data.posts) {
    if (post.post_analysis) {
      for (const key of ['prompt_sha256', 'input_sha256', 'cache_key', 'request_id']) delete post.post_analysis[key]
    }
    if (withoutMedia) post.archive.media = []
  }

  const paths = checkDashboard(data)
  const raw = JSON.stringify(data, null, 2) + '\n'
  if (sensitiveText.test(raw)) throw new Error('静态快照包含疑似密钥或本机路径，请人工核对。')
  for (const path of paths) {
    await checkImage(new URL('media/' + path.split('/').at(-1), archive), path)
  }

  // Remove only stale files from the generated candidate.
  await mkdir(privateSnapshot, { recursive: true })
  for (const path of await filesIn(privateSnapshot)) {
    if (path !== 'data/dashboard.json' && !paths.has(path)) await unlink(new URL(path, privateSnapshot))
  }
  await mkdir(new URL('data/archive-media/', privateSnapshot), { recursive: true })
  for (const path of paths) {
    await copyFile(new URL('media/' + path.split('/').at(-1), archive), new URL(path, privateSnapshot))
  }
  await writeFile(new URL('data/dashboard.json', privateSnapshot), raw)
  await validateResearchSnapshot(privateSnapshot)
  return { posts: data.posts.length, briefs: data.brief_runs.length, media: paths.size }
}
