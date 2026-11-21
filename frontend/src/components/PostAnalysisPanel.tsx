import { ChevronDown, Sparkles } from 'lucide-react'
import type { PostAnalysis, PostAnalysisExample } from '../model'
import { Badge } from './ui/badge'

const sourceLabels = { body: '存档正文', quote: '引用帖子', image: '图片观察' }
const verification = { pending: '待核验', missing: '无可核验链接', verified: '来源已核验' }

function ClaimLabels({ category }: { category: 'fact' | 'opinion' }) {
  return category === 'fact'
    ? <><Badge tone="fact">事实性陈述</Badge><Badge>尚未独立核实</Badge></>
    : <Badge tone="opinion">观点</Badge>
}

export function PostAnalysisPanel({ result, example }: {
  result?: PostAnalysis
  example?: PostAnalysisExample
}) {
  const displayed = result ?? example
  if (!displayed) return <p className="archive-analysis-empty">尚未生成 AI 解读</p>

  const content = displayed.analysis
  const firstClaim = content.claim_annotations[0]
  const sharedClaimCategory = firstClaim && content.claim_annotations.every(claim => claim.category === firstClaim.category)
    ? firstClaim.category
    : undefined
  const hasSource = content.author_opinion || content.claim_annotations.length > 0
  const hasResearch = content.why_it_matters || content.investment_implication ||
    content.research_value === 'actionable' || content.related_companies.length > 0

  return (
    <section className="archive-analysis-content" aria-label="AI 投研解读">
      <header className="analysis-panel-heading">
        <h4><Sparkles size={19} aria-hidden="true" />AI 投研解读</h4>
        {!result && <Badge tone="demo">示例解读 · 未调用模型</Badge>}
      </header>

      {content.summary && <section className="analysis-highlight">
        <h5>核心研究信号</h5><p>{content.summary.text}</p>
      </section>}
      {content.research_value === 'background' &&
        <p>该信息目前主要为一般性观点或背景材料，暂未形成可验证的投资研究线索。</p>}

      {hasSource && <section className="analysis-stage analysis-stage--source">
        <h5 className="analysis-stage-title"><span>01</span> · 来源信息与作者观点</h5>
        <div className="analysis-stage-fields">
          {content.author_opinion && <section className="analysis-field">
            <div className="analysis-field-heading"><h6>作者的核心判断</h6><Badge tone="opinion">作者观点</Badge></div>
            <p>{content.author_opinion.text}</p>
          </section>}
          {content.claim_annotations.length > 0 && <section className="analysis-field">
            <div className="analysis-field-heading">
              <h6>可核实陈述</h6>{sharedClaimCategory && <ClaimLabels category={sharedClaimCategory} />}
            </div>
            <ul className="analysis-claims">{content.claim_annotations.map((claim, index) => (
              <li key={index}>
                {!sharedClaimCategory && <div className="analysis-field-heading">
                  <strong className="analysis-attribution">{claim.attribution}</strong><ClaimLabels category={claim.category} />
                </div>}
                <p>{sharedClaimCategory && <strong className="analysis-attribution">{claim.attribution}</strong>}{claim.text}</p>
              </li>
            ))}</ul>
          </section>}
        </div>
      </section>}

      {hasResearch && <section className="analysis-stage analysis-stage--research">
        <h5 className="analysis-stage-title"><span>02</span> · 投资研究分析</h5>
        <div className="analysis-stage-fields">
          {content.why_it_matters && <section className="analysis-field">
            <h6>为什么值得关注</h6>
            <p>{content.why_it_matters.text}</p>
          </section>}
          {content.investment_implication && <section className="analysis-field">
            <div className="analysis-field-heading">
              <h6>潜在投资含义</h6><Badge tone="inference">{result ? 'AI 推断' : '推断示例'}</Badge>
            </div>
            <p>{content.investment_implication.text}</p>
          </section>}
          {content.research_value === 'actionable' && <section className="analysis-field">
            <div className="analysis-field-heading">
              <h6>反方假设与证据</h6>
              {content.risk_hypotheses.length > 0 && <Badge tone="inference">{result ? 'AI 反方假设' : '反方假设示例'}</Badge>}
            </div>
            {content.risk_hypotheses.length > 0 && <div className="analysis-counter">
              <ul>{content.risk_hypotheses.map((item, index) => <li key={index}>{item.text}</li>)}</ul>
            </div>}
            <div className="analysis-counter">
              <p className="analysis-note"><strong>已有反方证据</strong></p>
              {content.counterevidence.length ? <ul>{content.counterevidence.map((item, index) => (
                <li key={index}>{item.text}</li>
              ))}</ul> : <p className="analysis-note">本次样本未提供反方证据。</p>}
            </div>
          </section>}
          {content.related_companies.length > 0 &&
            <p className="analysis-note">关联公司　{content.related_companies.join('、')}</p>}
        </div>
      </section>}

      <section className="analysis-stage analysis-stage--followup">
        <h5 className="analysis-stage-title"><span>03</span> · 后续验证与证据</h5>
        <div className="analysis-stage-fields">
          {content.next_research_actions.length > 0 && <section className="analysis-highlight">
            <h6>下一步验证</h6>
            <ol>{content.next_research_actions.map((item, index) => <li key={index}>{item.text}</li>)}</ol>
          </section>}
          <details className="analysis-sources">
            <summary><span>证据引用</span><ChevronDown size={16} aria-hidden="true" /></summary>
            {result && <p className="analysis-note">{result.model_name} · {result.prompt_version} · <time dateTime={result.generated_at}>{result.generated_at.slice(0, 10)}</time></p>}
            {displayed.media_analysis_status === 'not_analyzed' && <p className="analysis-note">图片未分析</p>}
            {displayed.media_analysis_status === 'partial' && <p className="analysis-note">部分图片有观察结果</p>}
            {Object.entries(displayed.evidence).map(([id, evidence]) => (
              <div className="analysis-reference" key={id}>
                <p className="analysis-note">
                  <strong>{sourceLabels[evidence.kind]}</strong>
                  {evidence.attribution && ' · ' + evidence.attribution} · {verification[evidence.source_verification]}
                  {evidence.source_url && <>　<a className="text-link" href={evidence.source_url} target="_blank" rel="noreferrer">查看来源</a></>}
                </p>
                {!result && <p>{evidence.excerpt}</p>}
              </div>
            ))}
          </details>
        </div>
      </section>
    </section>
  )
}
