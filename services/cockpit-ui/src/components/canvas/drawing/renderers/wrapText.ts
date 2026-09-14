/** Break text into lines no wider than `maxWidth`, at spaces where it can. */
export function wrapText(text: string, maxWidth: number, width: (text: string) => number): string[] {
  const lines: string[] = []
  let line = ''
  for (const word of text.split(/\s+/).filter(Boolean)) {
    const candidate = line ? `${line} ${word}` : word
    if (width(candidate) <= maxWidth) {
      line = candidate
      continue
    }
    if (line) lines.push(line)
    if (width(word) <= maxWidth) {
      line = word
      continue
    }
    // A word wider than the box on its own is broken where it overflows.
    let piece = ''
    for (const char of word) {
      if (piece && width(piece + char) > maxWidth) {
        lines.push(piece)
        piece = ''
      }
      piece += char
    }
    line = piece
  }
  if (line) lines.push(line)
  return lines
}
