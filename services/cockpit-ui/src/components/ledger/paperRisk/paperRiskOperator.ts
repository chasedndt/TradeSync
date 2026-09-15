/** The operator name last used on this device, a convenience only; the server records who made each change. */

const KEY = 'paperRiskOperator'

export function rememberedOperator(): string {
  try {
    return localStorage.getItem(KEY) ?? ''
  } catch {
    return ''
  }
}

export function rememberOperator(name: string): void {
  try {
    localStorage.setItem(KEY, name.trim())
  } catch {
    // Storage unavailable: the name is simply typed again next time.
  }
}
