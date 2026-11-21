import { copyFile, mkdir, readFile } from 'node:fs/promises'

const source = new URL('../../data/processed/dashboard.json', import.meta.url)
const target = new URL('../public/data/dashboard.json', import.meta.url)
const dataset = JSON.parse(await readFile(source, 'utf8'))
if (dataset.schema_version !== 1 || dataset.mode !== 'demo' || !Array.isArray(dataset.posts) ||
    !dataset.posts.every((post) => post.is_demo === true && post.source_url === null)) {
  throw new Error('公开构建数据必须是已标记的合成演示样本。')
}
await mkdir(new URL('.', target), { recursive: true })
await copyFile(source, target)
