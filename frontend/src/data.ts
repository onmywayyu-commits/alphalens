import type { Dashboard } from './model.ts'

export async function loadDashboard(signal: AbortSignal): Promise<Dashboard> {
  const response = await fetch(new URL('data/dashboard.json', document.baseURI), { signal, cache: 'no-cache' })
  if (!response.ok) throw new Error('情报数据暂时无法读取。')
  const value = await response.json().catch(() => null)
  if (value?.schema_version !== 1 || !['demo', 'research'].includes(value.mode) ||
      !['accounts', 'posts', 'ideas', 'reports'].every((key) => Array.isArray(value[key]))) {
    throw new Error('情报数据格式不符合当前版本。')
  }
  const ids = new Set<string>()
  for (const post of value.posts) {
    const archive = value.mode === 'research'
    const id = archive ? post?.archive?.record_id : post?.post_id
    if (typeof id !== 'string' || !id || ids.has(id) ||
        (archive && (!Array.isArray(post.archive.media) || post.is_demo !== false))) {
      throw new Error('情报记录标识或存档格式不符合当前版本。')
    }
    ids.add(id)
  }
  return value
}
