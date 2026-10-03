export function filingLinks(sourceUrl: string, quote: string) {
  let url: URL
  try {
    url = new URL(sourceUrl)
  } catch {
    return null
  }
  if (url.protocol !== 'https:' && url.protocol !== 'http:') return null

  const anchor = url.hash.split(':~:')[0]
  url.hash = anchor
  const original = url.href
  // Converted filing text can add a space before a trademark superscript.
  const text = quote.replace(/\s+/g, ' ').replace(/\s+([®™])/g, '$1').trim()
  // A dash has special meaning in text fragments, but encodeURIComponent leaves it intact.
  const encoded = encodeURIComponent(text).replace(/-/g, '%2D')
  url.hash = `${anchor}:~:text=${encoded}`
  return { original, highlighted: text ? url.href : null }
}
