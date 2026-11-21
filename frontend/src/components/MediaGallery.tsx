import { useRef, useState } from 'react'
import { ImageOff, Maximize2, X } from 'lucide-react'
import type { ArchiveMedia } from '../model'
import { archiveImageUrl } from '../research'
import { Button } from './ui/button'

const unavailableLabels: Record<ArchiveMedia['availability'], string> = {
  available: '图片当前不可用', filename_match: '同名图片待核对', missing: '原始图片缺失',
  outside_archive: '图片尚未归档', conflict: '同名图片待核对', unreadable: '图片无法读取',
  invalid_file: '图片文件无法识别', unsupported_extension: '图片格式不受支持',
}

export function MediaGallery({ media, recordId }: { media: ArchiveMedia[]; recordId: string }) {
  const [failed, setFailed] = useState<ReadonlySet<string>>(new Set())
  const [active, setActive] = useState<{ item: ArchiveMedia; url: string } | null>(null)
  const dialog = useRef<HTMLDialogElement>(null)
  if (!media.length) return null

  function markFailed(id: string) {
    setFailed((previous) => new Set([...previous, id]))
  }

  return (
    <div className="archive-gallery">
      <ul className="archive-thumbnails" aria-label="存档图片">
        {media.map((item) => {
          const url = archiveImageUrl(item.preview_path, document.baseURI)
          const broken = failed.has(item.media_id)
          const label = `第 ${item.position} 张存档图片`
          return (
            <li key={item.media_id}>
              {url && !broken ? (
                <button type="button" className="archive-thumbnail" aria-label={`放大${label}`} onClick={() => {
                  setActive({ item, url })
                  dialog.current?.showModal()
                }}>
                  <img src={url} alt={label} loading="lazy" onError={() => markFailed(item.media_id)} />
                  <span aria-hidden="true"><Maximize2 size={13} />放大</span>
                </button>
              ) : (
                <div className="archive-image-message" title={item.original_filename}>
                  <ImageOff size={15} aria-hidden="true" /><span>{broken ? '图片加载失败' : unavailableLabels[item.availability]}</span>
                </div>
              )}
            </li>
          )
        })}
      </ul>
      <dialog ref={dialog} className="archive-image-dialog" aria-labelledby={`preview-${recordId}`}
        onClose={() => setActive(null)}
        onKeyDown={(event) => {
          if (event.key !== 'Escape') return
          event.preventDefault()
          event.stopPropagation()
          dialog.current?.close()
        }}
        onClick={(event) => {
          if (event.target === event.currentTarget) dialog.current?.close()
        }}>
        <div className="archive-image-panel">
          <header><h4 id={`preview-${recordId}`}>存档图片预览</h4>
            <Button className="button--quiet" autoFocus onClick={() => dialog.current?.close()} aria-label="关闭图片预览">
              <X size={18} aria-hidden="true" />
            </Button>
          </header>
          {active && (failed.has(active.item.media_id)
            ? <p className="archive-image-message" role="status">图片加载失败</p>
            : <img src={active.url} alt={`第 ${active.item.position} 张存档图片`}
                onError={() => markFailed(active.item.media_id)} />)}
          {active && <p className="archive-image-filename">{active.item.original_filename}</p>}
        </div>
      </dialog>
    </div>
  )
}

