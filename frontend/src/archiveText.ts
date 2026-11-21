/** Presentation only. Search, analysis and exports continue to use the archived text. */
export function formatArchiveText(content: string) {
  let formatted = content.replace(/^[ \t]*-[ \t]*(?=\r?$)/gm, '')
  const bullets = [...formatted.matchAll(/[ \t]+-(?=[ \t]+[“"''\p{L}$])/gu)]
  // A series beginning after a sentence or heading is a pasted list. A lone spaced dash is ambiguous.
  const firstBullet = bullets[0]
  if (bullets.length >= 2 && firstBullet && /[：:。！？；;!?”'）)]$/.test(formatted.slice(0, firstBullet.index))) {
    formatted = formatted.replace(/[ \t]+-(?=[ \t]+[“"''\p{L}$])/gu, '\n-')
  }

  // Require a consecutive numbered sequence and sentence boundaries to avoid changing decimal numbers.
  const sections = [...formatted.matchAll(/(^[ \t]*|[：:。！？；;!?][ \t]+|(?:\r?\n)[ \t]*)([1-9]\d?)[.．](?=[ \t]+\S)/g)]
  if (sections.length < 3 || !sections.every((section, index) => Number(section[2]) === index + 1)) return formatted

  return formatted.replace(/([：:。！？；;!?])[ \t]+(?=[1-9]\d?[.．][ \t]+\S)/g, '$1\n\n')
}
