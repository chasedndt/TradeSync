import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFile, readdir } from 'node:fs/promises'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'
import ts from 'typescript'

const SRC = fileURLToPath(new URL('../src/', import.meta.url))

// TradeSync is paper-only by construction. Labels such as "demo", "observe
// mode", "dry run" or "simulated" describe no state a user can act on, so they
// must not come back into anything the Cockpit renders.
const RETIRED = [/\bdemo\b/i, /\bobserve\b/i, /dry[\s_-]?run/i, /\bsimulat\w*/i]

// Attributes that never reach the screen as text.
const SILENT_ATTRIBUTES = new Set(['className', 'key', 'id', 'htmlFor', 'to', 'href', 'role', 'type', 'name', 'value', 'style'])
const EQUALITY = new Set([
  ts.SyntaxKind.EqualsEqualsEqualsToken,
  ts.SyntaxKind.ExclamationEqualsEqualsToken,
  ts.SyntaxKind.EqualsEqualsToken,
  ts.SyntaxKind.ExclamationEqualsToken,
])

async function sourceFiles(dir) {
  const files = []
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name)
    if (entry.isDirectory()) files.push(...(await sourceFiles(path)))
    else if (/\.(tsx?|jsx?)$/.test(entry.name) && !entry.name.endsWith('.d.ts')) files.push(path)
  }
  return files
}

/** A string literal that is code rather than copy: a type, an import, a key or a comparison operand. */
function isSilent(node) {
  const parent = node.parent
  if (!parent) return false
  if (ts.isImportDeclaration(parent) || ts.isExportDeclaration(parent) || ts.isLiteralTypeNode(parent)) return true
  if ((ts.isPropertyAssignment(parent) || ts.isPropertySignature(parent)) && parent.name === node) return true
  if (ts.isElementAccessExpression(parent) && parent.argumentExpression === node) return true
  if (ts.isBinaryExpression(parent) && EQUALITY.has(parent.operatorToken.kind)) return true
  if (ts.isCaseClause(parent)) return true
  if (ts.isJsxAttribute(parent) && SILENT_ATTRIBUTES.has(parent.name.getText())) return true
  return false
}

/** Every piece of text a component can render: JSX text, attribute values and string or template literals. */
export function renderedStrings(fileName, text) {
  const kind = fileName.endsWith('x') ? ts.ScriptKind.TSX : ts.ScriptKind.TS
  const source = ts.createSourceFile(fileName, text, ts.ScriptTarget.Latest, true, kind)
  const found = []
  const add = (value, node) => {
    const line = source.getLineAndCharacterOfPosition(node.getStart(source)).line + 1
    found.push({ value, line })
  }
  const visit = (node) => {
    if (ts.isJsxText(node)) {
      const value = node.getText(source).trim()
      if (value) add(value, node)
    } else if ((ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) && !isSilent(node)) {
      add(node.text, node)
    } else if (ts.isTemplateExpression(node)) {
      add([node.head.text, ...node.templateSpans.map((span) => span.literal.text)].join(' '), node)
    }
    ts.forEachChild(node, visit)
  }
  visit(source)
  return found
}

test('the scanner finds JSX text, attributes and template strings, and skips code', () => {
  const sample = [
    "import demo from './demo'",
    "type Mode = 'observe' | 'manual'",
    'const label = `Demo ${count}`',
    "export const A = () => <div title=\"Dry run\" className=\"observe\">Simulated fill {mode === 'observe' ? 'x' : 'y'}</div>",
  ].join('\n')
  const values = renderedStrings('sample.tsx', sample).map((s) => s.value)
  assert.ok(values.some((v) => v.startsWith('Demo')))
  assert.ok(values.includes('Dry run'))
  assert.ok(values.includes('Simulated fill'))
  assert.ok(!values.includes('observe'))
  assert.ok(!values.includes('./demo'))
})

test('no rendered Cockpit string uses retired execution wording', async () => {
  const offences = []
  for (const file of await sourceFiles(SRC)) {
    const text = await readFile(file, 'utf8')
    for (const { value, line } of renderedStrings(file, text)) {
      if (RETIRED.some((pattern) => pattern.test(value))) {
        offences.push(`${relative(SRC, file)}:${line}: ${value.slice(0, 120)}`)
      }
    }
  }
  assert.deepEqual(offences, [])
})
