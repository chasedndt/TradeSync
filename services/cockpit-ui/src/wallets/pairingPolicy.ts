/** Address discovery only. Never expand methods to make an incompatible wallet connect. */
export const ADDRESS_ONLY_NAMESPACES = {
  eip155: { chains: ['eip155:1'], methods: [] as string[], events: [] as string[] },
}

export function publicAddresses(namespaces: Record<string, { accounts: string[]; methods: string[] }>): string[] {
  if (Object.keys(namespaces).some((key) => key !== 'eip155' && key !== 'eip155:1')) throw new Error('Unexpected wallet namespace')
  const result: string[] = []
  for (const value of Object.values(namespaces)) {
    if (value.methods.length) throw new Error('Signing permissions are not accepted')
    for (const account of value.accounts) {
      if (!/^eip155:1:0x[0-9a-fA-F]{40}$/.test(account)) throw new Error('Unsupported account')
      result.push(account.split(':')[2])
    }
  }
  if (!result.length) throw new Error('No public account returned')
  return [...new Set(result)]
}

/** Keep relay session material in memory, not localStorage or the TradeSync database. */
export function memoryStorage() {
  const entries = new Map<string, unknown>()
  return {
    async getKeys() { return [...entries.keys()] },
    async getEntries<T>() { return [...entries.entries()] as [string, T][] },
    async getItem<T>(key: string) { return entries.get(key) as T | undefined },
    async setItem<T>(key: string, value: T) { entries.set(key, value) },
    async removeItem(key: string) { entries.delete(key) },
  }
}
