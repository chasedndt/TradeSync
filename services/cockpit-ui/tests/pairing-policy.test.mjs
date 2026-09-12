import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import ts from 'typescript'

const source = await readFile(new URL('../src/wallets/pairingPolicy.ts', import.meta.url), 'utf8')
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2020 } }).outputText
const { ADDRESS_ONLY_NAMESPACES, publicAddresses, memoryStorage } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`)
const account = 'eip155:1:0x' + 'a'.repeat(40)
test('proposal grants no methods', () => assert.deepEqual(ADDRESS_ONLY_NAMESPACES.eip155.methods, []))
test('valid EVM address extracted and deduplicated', () => assert.deepEqual(publicAddresses({ eip155: { accounts: [account, account], methods: [] } }), ['0x' + 'a'.repeat(40)]))
test('signing grants refused', () => assert.throws(() => publicAddresses({ eip155: { accounts: [account], methods: ['personal_sign'] } })))
test('unexpected chain refused', () => assert.throws(() => publicAddresses({ eip155: { accounts: [account.replace(':1:', ':137:')], methods: [] } })))
test('Solana namespace refused', () => assert.throws(() => publicAddresses({ solana: { accounts: ['abc'], methods: [] } })))
test('empty session refused', () => assert.throws(() => publicAddresses({})))
test('malformed address refused', () => assert.throws(() => publicAddresses({ eip155: { accounts: ['eip155:1:secret'], methods: [] } })))
test('memory stores do not share or persist state', async () => {
  const a = memoryStorage(), b = memoryStorage()
  await a.setItem('session', { test: true })
  assert.equal(await b.getItem('session'), undefined)
  await a.removeItem('session')
  assert.deepEqual(await a.getKeys(), [])
})
