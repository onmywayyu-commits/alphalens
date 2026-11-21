import { useEffect, useState } from 'react'
import { ArrowUp } from 'lucide-react'

const scrollThreshold = 300

export function BackToTop({ focusTargetId }: { focusTargetId: string }) {
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    function updateVisibility() {
      setVisible(window.scrollY > scrollThreshold)
    }

    updateVisibility()
    window.addEventListener('scroll', updateVisibility, { passive: true })
    return () => window.removeEventListener('scroll', updateVisibility)
  }, [])

  function scrollToTop() {
    document.getElementById(focusTargetId)?.focus({ preventScroll: true })
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    window.scrollTo({ top: 0, behavior: reduceMotion ? 'instant' : 'smooth' })
  }

  return (
    <button type="button" className="back-to-top" aria-label="回到顶部" inert={!visible}
      data-visible={visible} onClick={scrollToTop}>
      <ArrowUp size={21} aria-hidden="true" />
    </button>
  )
}
