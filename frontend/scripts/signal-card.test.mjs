import assert from 'node:assert/strict'
import { test } from 'node:test'
import { groupSignalEvidence } from '../src/signal-card.ts'

test('SSD 两条转述加作者观点落在同一条存档，重复引用只合并一次', () => {
  const original = { record_id: 'archive-ssd', excel_row: 3, kind: 'body', source_verification: 'pending',
    source_url: 'https://x.com/aleabitoreddit/status/2123633356969775107' }
  const data = {
    'ssd-gpu': { category: 'fact', text: 'Serenity 转述 Phison CEO 的看法。',
      citations: [{ ...original, excerpt: '需求放缓与 GPU 供应有关' }] },
    'ssd-prepayments': { category: 'fact', text: '同帖转述预付款的影响。',
      citations: [{ ...original, excerpt: '预付款可能延后其他零件采购' }] },
    'ssd-deferral': { category: 'opinion', text: 'Serenity 认为采购延迟。',
      citations: [{ ...original, excerpt: '这是延后采购' }] },
  }
  const groups = groupSignalEvidence(data, ['ssd-gpu', 'ssd-prepayments', 'ssd-deferral', 'ssd-gpu'])
  assert.equal(groups.length, 1)
  assert.equal(groups[0].excelRow, 3)
  assert.deepEqual(groups[0].items.map(({ item }) => item.category), ['fact', 'fact', 'opinion'])
  assert.equal(groups[0].items[0].citations[0].source_verification, 'pending')
  assert.equal(groups[0].items[0].citations[0].source_url, original.source_url)
})
