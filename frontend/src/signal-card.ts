import type { BriefRunData, SignalCompanyScope, ThesisStatus } from './model.ts'

export interface SignalCopy {
  title?: string
  judgment?: string
  reason?: string
  why?: string
  implication?: string
  risk?: string
  action?: string[]
  companyScope?: SignalCompanyScope
  thesisStatus?: ThesisStatus
  statements?: Record<string, string>
}

const reviewedNovember20: Record<string, SignalCopy> = {
  'essd-purchase-timing': {
    title: '企业级 SSD 需求放缓：采购延后还是需求转弱？',
    judgment: '现有线索支持关注 GPU 供应对采购节奏的影响。仍需等待到货改善后的订单表现，才能判断终端需求是否转弱。',
    reason: '区分采购延后和需求转弱，有助于判断存储供应商的盈利压力会持续多久。',
    why: '若 GPU 到货延迟拖慢服务器部署，企业级 SSD 出货和相关收入确认可能后移，短期库存周转也可能承压。',
    implication: '若供应约束是主因，GPU 到货改善后，企业级 SSD 新订单应先企稳，随后反映到出货和收入指引。',
    risk: '云厂商若同时压减资本开支、降低单台服务器的存储配置或更换供应商，到货改善也未必带来原供应商订单回升。',
    action: ['未来一至两个季度，按季对照云厂商 GPU 到货进度、存储供应商的企业级 SSD 新订单与出货、库存周转及收入指引。若到货改善后订单仍弱，降低采购仅是延后的判断。'],
    thesisStatus: 'to_validate',
    companyScope: { direct: ['Phison'], value_chain: ['SanDisk · SNDK', 'Kioxia'] },
    statements: {
      'ssd-gpu': '据 Serenity 转述，Phison CEO 将近期中国企业级 SSD 需求放缓与 GPU 短缺联系起来。',
      'ssd-prepayments': '同一帖还转述了部分中国云厂商的 GPU 预付款可能延后其他组件采购的说法。',
      'ssd-deferral': 'Serenity 将这轮放缓解读为采购延后。',
    },
  },
  'liquid-rack-retrofit': {
    title: '重载液冷机架会限制旧机房承接 AI 容量吗？',
    judgment: '硬件规格只能界定改造条件。可交付容量还取决于实际楼板评级、设备布局和停机安排。',
    reason: '承载能力可用工程规格核对，并可能改变改造与新建项目的相对成本。',
    why: '若机架荷载超过设计限值，楼板加固会抬高单位机柜资本开支，施工停机也可能延后出租和收入确认。',
    implication: '若旧机房合规改造后的单位可交付容量成本接近新建项目，同时交付更晚，运营商可能更偏向专用新建机房。',
    risk: '减小单机柜密度或重新布置设备可能降低改造幅度。存档中的机架与楼板参数来自同一线程，具体站点仍需单独核对。',
    action: ['选两处存量机房，按设备规格核对满载点荷载、楼板额定值和停机天数，比较改造与新建的单位可交付 MW 成本及投产日期。'],
    thesisStatus: 'to_validate',
    companyScope: { direct: ['NVIDIA · NVDA'], value_chain: ['数据中心运营商'] },
  },
  'gpu-residual-value': {
    title: '二手 GPU 价格能否支撑更高的回收残值？',
    judgment: 'Ornn 的样本提供残值线索。贷款人与出租方应以可成交净价和实际退出周期为估值依据。',
    reason: '可回收价值会影响租赁回报和抵押融资条件，且能按型号用成交核对。',
    why: '在租金和持有期相近时，退出净价越高，出租方的全周期回收额越高，贷款人的抵押损失也可能下降。',
    implication: '若同型号、同服役期设备的净成交价持续高于对应账面净值，且成交周期没有拉长，可检验五年折旧假设是否低估部分设备的经济残值。',
    risk: '报价可能高于成交净价。维修、拆装与经纪费用会减少实际回收额，新型号换代可能拉长旧设备的退出周期。',
    action: ['取近 90 天 H100 与更新型号的实际成交，按服役期和保修配对。对照扣除处置费用后的价格、成交笔数、中位成交周期和账面净值。'],
    thesisStatus: 'to_validate',
    companyScope: { direct: ['NVIDIA · NVDA（设备型号）'], value_chain: ['GPU 出租方', '抵押贷款人'] },
  },
}

const reviewedNovember19: Record<string, SignalCopy> = {
  'optical-order-conversion': {
    title: '光互连产能预留能否转化为付费出货？',
    judgment: '协议金额提供需求线索。收入可见度仍取决于采购义务、交付节奏和客户验收。',
    reason: '产能承诺和量产节点可分别用合同条款与出货数据核对。',
    why: '有约束的采购义务更有利于排产。量产良率与产能利用率影响单位制造成本，进而影响收入转化后的毛利。',
    implication: '若最低采购义务落实为订单且光子 SOI 或近封装光学出货按期放量，可上调相关供应商收入的可见度。',
    risk: '协议可能分年兑现或保留取消条款。涉及协议与量产的线索集中在同一作者。',
    action: ['在下一次财报及公告中核对最低采购量、首个量产交付期、相关产品收入和毛利率，区分协议名义规模与当期确认金额。'],
    thesisStatus: 'to_validate',
    companyScope: { direct: ['Soitec', 'Coherent · COHR'], value_chain: ['光互连材料与器件商'] },
  },
  'cloud-capex-decoupling': {
    title: 'AI 用量增长时，云厂商资本开支还能放缓吗？',
    judgment: '效率提升可能降低单位算力支出。总资本开支仍取决于新增用量和部署规模。',
    reason: '资本开支与 AI 用量增速的差异会影响上游硬件收入预期。',
    why: '在相同工作量下，设备降价和利用率提高可降低新增算力的购置成本，削弱用量增长向硬件支出的传导。',
    implication: '若 AI 用量继续增长而单位推理成本和新增设备支出同步下降，按用量增速外推硬件订单的预期可能偏高。',
    risk: '推理需求若超预期，新增部署可能抵消效率改善。当前线索来自一家公司的转述。',
    action: ['在下次财报对照腾讯的资本开支、AI 用量或替代指标、设备单价和集群利用率，并用同业指引验证。'],
    thesisStatus: 'to_validate',
    companyScope: { direct: ['腾讯'], value_chain: ['AI 服务器与加速器供应商'] },
  },
}

export function reviewedSignal(runId: string, eventKey: string): SignalCopy | undefined {
  if (runId === '2987765148da8ebc9b37f02659f4ee231eaf8280ab0176f14299827130229af2') return reviewedNovember20[eventKey]
  if (runId === '61479a8338905297f40ad4227ac02926965c803e3660717a64b13f14371c48ed') return reviewedNovember19[eventKey]
}

type Evidence = BriefRunData['evidence'][string]
type Citation = Evidence['citations'][number]

export function groupSignalEvidence(
  evidence: BriefRunData['evidence'], ids: string[],
) {
  const groups = new Map<string, { recordId: string; excelRow: number; items: { id: string; item: Evidence; citations: Citation[] }[] }>()
  for (const id of new Set(ids)) {
    const item = evidence[id]
    if (!item) continue
    for (const citation of item.citations) {
      const { record_id, excel_row } = citation
      let group = groups.get(record_id)
      if (!group) {
        group = { recordId: record_id, excelRow: excel_row, items: [] }
        groups.set(record_id, group)
      }
      const entry = group.items.find((value) => value.id === id)
      if (entry) entry.citations.push(citation)
      else group.items.push({ id, item, citations: [citation] })
    }
  }
  return [...groups.values()]
}
