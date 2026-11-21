import assert from 'node:assert/strict'
import { test } from 'node:test'
import { filterRadar, radarTheses } from '../src/radar.ts'

function claim(row, source, category = 'fact') {
  return { category, text: '存档陈述', citations: [{
    record_id: 'row-' + row, excel_row: row, kind: 'body', source_post_id: source, source_verification: 'pending',
  }] }
}

function signal(event_key, ids, related_tickers) {
  return {
    event_key, title: event_key, what_happened: ids, bull_case: ids, bear_case: [],
    related_tickers, related_sectors: [], thesis_status: 'strengthened',
    investment_implication: '待检验的判断', next_research_action: '核对后续资料',
  }
}

const data = {
  mode: 'research', relations: [{ kind: 'numbered_thread_candidate', record_ids: ['row-17', 'row-18', 'row-19'] }],
  brief_runs: [
    { date: '2026-11-20', mode: 'replay', evidence: {
      ssd: claim(3, 'ssd'), ssd2: claim(3, 'ssd'), rack: claim(17, 'rack'), floor: claim(18, 'rack'),
      retrofit: claim(19, 'rack-later'), 'optical-value': claim(5, 'other', 'opinion'),
    }, daily_v2: {
      top_signals: [
        signal('essd-purchase-timing', ['ssd', 'ssd2'], ['Phison', 'SanDisk · SNDK']),
        signal('liquid-rack-retrofit', ['rack', 'floor', 'retrofit'], ['NVIDIA · NVDA']),
      ],
      research_themes: [{ theme_key: 'optical-interconnect', item_ids: ['optical-value'] }],
    } },
    { date: '2026-11-19', mode: 'replay', evidence: { optical: claim(9, 'optical') }, daily_v2: {
      top_signals: [signal('optical-order-conversion', ['optical'], ['Soitec'])], research_themes: [],
    } },
  ],
}

test('雷达按归档建立假设，按帖和线程合并来源，后续观点不更新状态', () => {
  const [ssd, optics, rack] = radarTheses(data)
  assert.equal(ssd.timeline[0].groups.length, 1)
  assert.equal(ssd.timeline[0].groups[0][0].items.length, 2)
  assert.equal(rack.timeline[0].groups.length, 1)
  assert.deepEqual(rack.timeline[0].groups[0].map(({ excelRow }) => excelRow), [17, 18, 19])
  assert.deepEqual(optics.timeline.map(({ date, kind }) => [date, kind]), [
    ['2026-11-19', 'initial'], ['2026-11-20', 'context'],
  ])
  assert.deepEqual(optics.timeline[1].support, [])
  assert([ssd, optics, rack].every(({ status }) => status === 'to_validate'))
})

test('检索支持主题、公司、大小写和全角代码，状态筛选不捏造结果', () => {
  const theses = radarTheses(data)
  assert.deepEqual(filterRadar(theses, 'ＳＮＤＫ phison', '存储供需', 'to_validate').map(({ name }) => name), ['企业级 SSD'])
  assert.deepEqual(filterRadar(theses, 'NVIDIA', '', '').map(({ name }) => name), ['液冷机房'])
  assert.deepEqual(filterRadar(theses, '', '光互连', '').map(({ name }) => name), ['光互连'])
  assert.deepEqual(filterRadar(theses, '', '', 'strengthened'), [])
})
