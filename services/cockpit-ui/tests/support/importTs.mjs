import { readFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import ts from 'typescript'

/**
 * Import a TypeScript module from the cockpit source the way the existing tests
 * do (transpile, then import it as a data URL), following its relative imports
 * so a module split across several small files can be tested whole.
 *
 * Only relative imports are followed. A module tested this way must not import
 * a package at runtime; type-only imports are erased and are fine.
 */
const COCKPIT_ROOT = fileURLToPath(new URL('../../', import.meta.url))
const built = new Map()

export async function importTs(pathFromCockpitRoot) {
  return import(await moduleUrl(resolve(COCKPIT_ROOT, pathFromCockpitRoot)))
}

function moduleUrl(path) {
  if (!built.has(path)) built.set(path, build(path))
  return built.get(path)
}

async function build(path) {
  const source = await readFile(path, 'utf8')
  let code = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2020 },
    fileName: path,
  }).outputText
  const specifiers = new Set(Array.from(code.matchAll(/\bfrom\s+(['"])(\.{1,2}\/[^'"]+)\1/g), (match) => match[2]))
  for (const specifier of specifiers) {
    const target = resolve(dirname(path), /\.tsx?$/.test(specifier) ? specifier : `${specifier}.ts`)
    const url = await moduleUrl(target)
    code = code.split(`'${specifier}'`).join(`'${url}'`).split(`"${specifier}"`).join(`"${url}"`)
  }
  return `data:text/javascript;base64,${Buffer.from(code).toString('base64')}`
}
