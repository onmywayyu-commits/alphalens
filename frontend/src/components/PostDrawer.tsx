import { useLayoutEffect, useRef } from 'react'
import { ArrowUpRight, X } from 'lucide-react'
import type { ArchiveRelation, Post } from '../model'
import { formatArchiveText } from '../archiveText'
import { formatTime, recordKey } from '../research'
import { archiveLink, PostIdentity, postSource, quotedPostSource, type PostDetail } from './ArchiveCard'
import { EvidenceSections } from './EvidenceSections'
import { MediaGallery } from './MediaGallery'
import { PostAnalysisPanel } from './PostAnalysisPanel'
import { Button } from './ui/button'

export function PostDrawer({ post, detail, onSelect, onDismiss, relations, href }: {
  post: Post | undefined
  detail: PostDetail
  onSelect: (detail: PostDetail) => void
  onDismiss: () => void
  relations: ArchiveRelation[]
  href: (id: string) => string
}) {
  const dialog = useRef<HTMLDialogElement>(null)
  const scrollBody = useRef<HTMLDivElement>(null)
  const bodySection = useRef<HTMLElement>(null)
  const quoteSection = useRef<HTMLElement>(null)
  const analysisSection = useRef<HTMLElement>(null)

  useLayoutEffect(() => {
    const panel = dialog.current
    if (!panel) return
    if (!post) {
      if (panel.open) panel.close()
      return
    }
    if (!panel.open) panel.showModal()

    const scroll = scrollBody.current
    const section = detail === 'analysis' ? analysisSection.current :
      detail === 'quote' ? quoteSection.current ?? bodySection.current : bodySection.current
    if (scroll && section) {
      scroll.scrollTop = section === bodySection.current ? 0 :
        scroll.scrollTop + section.getBoundingClientRect().top - scroll.getBoundingClientRect().top - 12
      section.focus({ preventScroll: true })
    }
  }, [post, detail])

  const archive = post?.archive
  const source = post && postSource(post)
  const quote = quotedPostSource(archive)
  const quotedRecords = archive ? relations
    .filter((relation) => relation.kind === 'archive_quote' && relation.record_ids[0] === archive.record_id)
    .flatMap((relation) => relation.record_ids.slice(1).map((id, index) => ({ id, row: relation.excel_rows[index + 1] }))) : []
  const hasQuote = Boolean(archive?.quoted_content?.trim() || quote || quotedRecords.length)

  return (
    <dialog id="post-drawer" ref={dialog} className="post-drawer" aria-labelledby="post-drawer-title"
      onCancel={(event) => {
        if (event.target !== event.currentTarget) return
        event.preventDefault()
        onDismiss()
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget) onDismiss()
      }}>
      {post && <>
        <header className="post-drawer-header">
          <PostIdentity post={post} titleId="post-drawer-title" />
          <Button className="button--quiet post-drawer-close" aria-label="关闭情报详情" onClick={onDismiss}>
            <X size={22} aria-hidden="true" />
          </Button>
        </header>
        <nav className="post-drawer-nav" aria-label="情报详情">
          <Button className="button--quiet" aria-current={detail !== 'analysis' ? 'location' : undefined}
            onClick={() => onSelect('body')}>全文</Button>
          <Button className="button--quiet" aria-current={detail === 'analysis' ? 'location' : undefined}
            onClick={() => onSelect('analysis')}>AI 投研解读</Button>
          {source && <a className="text-link" href={source} target="_blank" rel="noreferrer">
            查看 X 原帖 <ArrowUpRight size={15} aria-hidden="true" />
          </a>}
        </nav>
        <div ref={scrollBody} className="post-drawer-body" key={recordKey(post)}>
          <section ref={bodySection} tabIndex={-1} className="post-drawer-section" aria-label="全文">
            {post.title && !archive && <h4>{post.title}</h4>}
            {post.summary && !archive && <p className="post-drawer-summary">{post.summary}</p>}
            <div className="post-drawer-fulltext">
              {formatArchiveText(post.content).split(/\r?\n(?:[ \t]*\r?\n)+/).map((paragraph, index) =>
                <p className="archive-body" key={index}>{paragraph}</p>
              )}
            </div>
            {!archive && post.collected_at && <small>采集时间　<time dateTime={post.collected_at}>{formatTime(post.collected_at)}</time></small>}
            {archive && <MediaGallery media={archive.media} recordId={archive.record_id} />}
            {archive && hasQuote && <section ref={quoteSection} tabIndex={-1} className="archive-quote" aria-labelledby="post-drawer-quote-title">
              <h4 id="post-drawer-quote-title">引用帖子 {archive.quoted_author_handle && <small translate="no">{archive.quoted_author_handle}</small>}</h4>
              {archive.quoted_content?.trim() && <p>{formatArchiveText(archive.quoted_content)}</p>}
              {quote && <a className="text-link" href={quote} target="_blank" rel="noopener noreferrer">查看引用原帖 <ArrowUpRight size={14} aria-hidden="true" /></a>}
              {quotedRecords.map(({ id, row }) => <a className="text-link" key={id} href={href(id)}>查看关联存档（第 {row} 行）</a>)}
            </section>}
          </section>
          <section ref={analysisSection} tabIndex={-1} className="post-drawer-section post-drawer-analysis" aria-label="AI 投研解读">
            {post.evidence.length > 0 && !archive && !post.post_analysis
              ? <EvidenceSections evidence={post.evidence} />
              : <PostAnalysisPanel result={post.post_analysis} example={post.post_analysis_example} />}
          </section>
        </div>
      </>}
    </dialog>
  )
}
