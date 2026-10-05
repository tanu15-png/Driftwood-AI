// Docling's triplet serializer repeats the row label before every column.
// Convert complete triplet lines for display only; evidence stays verbatim.
export function formatFilingTables(text: string): string {
  return text.split('\n').map((line) => {
    const cells = [...line.matchAll(/(?:^|\. )(.+?|), (\d+) = ([\s\S]*?)(?=\. (?:.+?|), \d+ = |$)/g)]
    if (cells.length < 2 || cells[0].index !== 0) return line
    if (cells.map((cell) => cell[0]).join('') !== line) return line
    const rows: string[][] = []
    let previousColumn = 0
    let label = ''
    for (const cell of cells) {
      const column = Number(cell[2])
      if (column > 100 || column < 1) return line
      if (column <= previousColumn || cell[1] !== label) rows.push([])
      if (!rows.length) rows.push([])
      rows[rows.length - 1][column - 1] = cell[3]
      previousColumn = column
      label = cell[1]
    }
    const width = Math.max(...rows.map((row) => row.length))
    const escape = (value: string) => value.replaceAll('|', '\\|')
    const rowText = (row: string[]) => `| ${Array.from({ length: width }, (_, index) => escape(row[index] ?? '')).join(' | ')} |`
    // Numeric column labels are supplied by the serializer, not inferred headers.
    return ['\n' + rowText(Array.from({ length: width }, (_, index) => `Column ${index + 1}`)),
      rowText(Array.from({ length: width }, () => '---')), ...rows.map(rowText), '\n'].join('\n')
  }).join('\n')
}
