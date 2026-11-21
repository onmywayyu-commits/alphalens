import { useState } from 'react'
import { ArrowUpRight, PanelRightOpen, Quote, Sparkles } from 'lucide-react'
import type { ArchivePost, Post } from '../model'
import { formatArchiveText } from '../archiveText'
import { archiveImageUrl, formatTime, postSectors, postTickers, recordKey } from '../research'
import { Badge } from './ui/badge'
import { Button } from './ui/button'

export type PostDetail = 'body' | 'analysis' | 'quote'

export function authorLabel(post: Post) {
  if (post.archive) return post.archive.author_display_name ?? post.archive.source_author_handle ?? '作者名称未记录'
  return post.is_demo ? post.author.replace(/^demo-scenario-/, '合成情境 ') : `@${post.author}`
}

export function archiveLink(raw: string | null) {
  if (!raw) return null
  try {
    const url = new URL(raw)
    if (!['x.com', 'twitter.com', 'www.x.com', 'www.twitter.com'].includes(url.host) ||
        url.protocol !== 'https:' || url.username || url.password) return null
    return /^\/(?:[\w]+|i\/web)\/status\/[0-9]+\/?$/.test(url.pathname) ? url.href : null
  } catch {
    return null
  }
}

export function postSource(post: Post) {
  if (post.is_demo || (post.archive && post.archive.source_url_status !== 'status')) return null
  return archiveLink(post.source_url)
}

export function quotedPostSource(archive?: ArchivePost) {
  return archive?.quoted_url_status === 'status' ? archiveLink(archive.quoted_url) : null
}

export function PostIdentity({ post, titleId }: { post: Post; titleId?: string }) {
  const name = authorLabel(post)
  const handle = post.archive?.source_author_handle ?? (!post.is_demo && post.author ? '@' + post.author : null)
  const date = post.archive?.posted_date ?? post.published_at
  return (
    <div className="archive-card-header">
      <span className="archive-avatar" aria-hidden="true">{Array.from(name)[0]?.toLocaleUpperCase()}</span>
      <div className="archive-card-author">
        <h3 id={titleId}>{name}</h3>
        <div className="archive-card-byline">
          {handle && handle !== name && <span translate="no">{handle}</span>}
          {date && <time dateTime={date}>{post.archive?.posted_date ?? formatTime(date)}</time>}
        </div>
      </div>
    </div>
  )
}

function ArchiveThumbnail({ src, position, onOpen }: {
  src: string
  position: number
  onOpen: () => void
}) {
  const [failed, setFailed] = useState(false)
  if (failed) return null

  return (
    <button type="button" className="archive-card-preview-image" onClick={onOpen}
      aria-label={'在情报详情中查看配图 ' + position} aria-haspopup="dialog" aria-controls="post-drawer">
      <img src={src} alt={'存档配图 ' + position} loading="lazy" onError={() => setFailed(true)} />
    </button>
  )
}

export function ArchiveCard({ post, onOpen }: {
  post: Post
  onOpen: (detail: PostDetail) => void
}) {
  const source = postSource(post)
  const quoteText = post.archive?.quoted_content
  const quoteAuthor = post.archive?.quoted_author_handle
  const quoteUrl = quotedPostSource(post.archive)
  const hasQuoteText = Boolean(quoteText?.trim())
  const thumbnails = (post.archive?.media ?? []).flatMap((item) => {
    const src = archiveImageUrl(item.preview_path, document.baseURI)
    return src ? [{ id: item.media_id, position: item.position, src }] : []
  })
  const analysis = post.post_analysis ?? post.post_analysis_example
  const tags = [...new Set([
    ...postSectors(post), ...postTickers(post),
    ...(analysis?.analysis.related_sectors ?? []), ...(analysis?.analysis.related_companies ?? []),
    ...(analysis?.analysis.related_tickers ?? []),
  ])]

  return (
    <article className="post-card archive-card" id={'record-' + recordKey(post)}>
      <header><PostIdentity post={post} /></header>
      {(tags.length > 0 || post.is_demo) && <div className="post-tags archive-card-tags">
        {tags.map((tag) => <Badge key={tag}>{tag}</Badge>)}
        {post.is_demo && <Badge tone="demo">合成样本</Badge>}
      </div>}
      <p className="archive-body archive-body--clamped">{formatArchiveText(post.content)}</p>
      {thumbnails.length > 0 && <div className="archive-card-images">
        {thumbnails.map(({ id, position, src }) => <ArchiveThumbnail key={id + src} src={src}
          position={position} onOpen={() => onOpen('body')} />)}
      </div>}
      {(hasQuoteText || quoteUrl) && <div className="archive-quote-preview">
        <button type="button" className="archive-quote-preview-open" onClick={() => onOpen('quote')}
          aria-label="在详情中查看引用帖子" aria-haspopup="dialog" aria-controls="post-drawer">
          <span className="archive-quote-preview-heading">
            <Quote size={14} aria-hidden="true" /><strong>引用帖子</strong>
            {quoteAuthor && <span translate="no">{quoteAuthor}</span>}
          </span>
          {hasQuoteText && <span className="archive-quote-preview-copy">{quoteText}</span>}
        </button>
        {quoteUrl && <a className="text-link archive-quote-preview-link" href={quoteUrl} target="_blank" rel="noopener noreferrer">
          {hasQuoteText ? '查看引用原帖' : '查看来源'} <ArrowUpRight size={13} aria-hidden="true" />
        </a>}
      </div>}
      <div className="archive-card-actions">
        <Button className="button--quiet archive-body-toggle" onClick={() => onOpen('body')} aria-haspopup="dialog" aria-controls="post-drawer">
          <PanelRightOpen size={15} aria-hidden="true" />展开全文
        </Button>
        <Button className="button--quiet archive-analysis-toggle" onClick={() => onOpen('analysis')} aria-haspopup="dialog" aria-controls="post-drawer">
          <Sparkles size={15} aria-hidden="true" />AI 投研解读
          {!post.post_analysis && post.post_analysis_example && <Badge tone="demo">示例</Badge>}
        </Button>
        {source && <a className="text-link" href={source} target="_blank" rel="noreferrer">
          查看 X 原帖 <ArrowUpRight size={15} aria-hidden="true" />
        </a>}
      </div>
    </article>
  )
}
