import { useLayoutEffect, useRef, type ReactNode } from 'react'

export function FeedMasonry({ children }: { children: ReactNode }) {
  const listRef = useRef<HTMLDivElement>(null)

  useLayoutEffect(() => {
    const list = listRef.current
    if (!list) return
    const cards = Array.from(list.querySelectorAll<HTMLElement>(':scope > .archive-card'))

    const arrange = () => {
      const styles = getComputedStyle(list)
      const columns = Number(styles.getPropertyValue('--feed-columns'))
      if (columns <= 1) {
        list.removeAttribute('data-masonry')
        list.style.removeProperty('height')
        return
      }

      list.setAttribute('data-masonry', '')
      const columnGap = parseFloat(styles.columnGap) || 0
      const rowGap = parseFloat(styles.rowGap) || 0
      const step = (list.getBoundingClientRect().width + columnGap) / columns
      const heights = cards.map((card) => card.getBoundingClientRect().height)
      const offsets = Array<number>(columns).fill(0)

      // Keep the input order in the DOM. The next card takes the earliest available spot.
      cards.forEach((card, index) => {
        const top = Math.min(...offsets)
        const column = offsets.indexOf(top)
        card.style.setProperty('--feed-card-x', `${column * step}px`)
        card.style.setProperty('--feed-card-y', `${top}px`)
        offsets[column] = top + heights[index] + rowGap
      })
      list.style.height = `${Math.max(0, Math.max(...offsets) - rowGap)}px`
    }

    arrange()
    const observer = new ResizeObserver(arrange)
    cards.forEach((card) => observer.observe(card, { box: 'border-box' }))
    window.addEventListener('resize', arrange)
    return () => {
      observer.disconnect()
      window.removeEventListener('resize', arrange)
    }
  }, [children])

  return <div className="post-list" ref={listRef}>{children}</div>
}
