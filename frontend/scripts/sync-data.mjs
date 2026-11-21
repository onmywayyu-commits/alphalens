import { copyFile, mkdir, readFile } from 'node:fs/promises'
import { preparePrivateSnapshot } from './static-research.mjs'

const args = process.argv.slice(2)
if (args[0] === '--prepare-pages-preview' && args.slice(1).every((arg) => arg === '--without-media')) {
  const result = await preparePrivateSnapshot({ withoutMedia: args.includes('--without-media') })
  console.log(`已准备本机静态快照：${result.posts} 条存档，${result.briefs} 份简报，${result.media} 张配图。`)
} else if (args.length === 0) {
  const source = new URL('../../data/processed/dashboard.json', import.meta.url)
  const target = new URL('../public/data/dashboard.json', import.meta.url)
  const dataset = JSON.parse(await readFile(source, 'utf8'))
  if (dataset.schema_version !== 1 || dataset.mode !== 'demo' || !Array.isArray(dataset.posts) ||
      !dataset.posts.every((post) => post.is_demo === true && post.source_url === null)) {
    throw new Error('合成样本模式需要已标记的演示数据。')
  }
  await mkdir(new URL('.', target), { recursive: true })
  await copyFile(source, target)
} else {
  throw new Error('用法：node scripts/sync-data.mjs [--prepare-pages-preview [--without-media]]')
}
