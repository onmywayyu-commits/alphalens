import assert from 'node:assert/strict'
import test from 'node:test'
import { formatArchiveText } from '../src/archiveText.ts'

test('正文显示保留已有换行、连字符、减法和小数', () => {
  const text = '首段\n\n第二段使用 HBM-4 和 NVDA - AMD，也保留 12 - 3 与 3.5。\r\n第三段。'
  assert.equal(formatArchiveText(text), text)
})

test('仅在连续编号和明显的分段结构下恢复换行', () => {
  assert.equal(formatArchiveText('转述： 1. 第一点。 2. 第二点。 3. 第三点。'),
    '转述：\n\n1. 第一点。\n\n2. 第二点。\n\n3. 第三点。')
  assert.equal(formatArchiveText('独立版本 1. 不需要分段。'), '独立版本 1. 不需要分段。')
})

test('独立分隔行转为空行，成组行内分段保留项目符号', () => {
  assert.equal(formatArchiveText('第一段\n-\n第二段'), '第一段\n\n第二段')
  assert.equal(formatArchiveText('要点： - 第一项 - 第二项'), '要点：\n- 第一项\n- 第二项')
})
