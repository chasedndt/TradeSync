import { useEffect, useRef, useState } from 'react'
import type SignClient from '@walletconnect/sign-client'
import { ADDRESS_ONLY_NAMESPACES, memoryStorage, publicAddresses } from '../wallets/pairingPolicy'

/** One-shot address sharing: close the session before handing off to watch-only reads. */
export function WalletPairing({ onAddress }: { onAddress: (address: string) => void }) {
  const [projectId, setProjectId] = useState('')
  const [busy, setBusy] = useState(false)
  const [qr, setQr] = useState('')
  const [accounts, setAccounts] = useState<string[]>([])
  const [message, setMessage] = useState('Setup required: supply your public WalletConnect/Reown project ID. Address lookup below works without it.')
  const attempt = useRef(0)
  const cleanup = useRef<(() => Promise<void>) | null>(null)
  useEffect(() => () => { attempt.current++; void cleanup.current?.() }, [])

  async function pair() {
    if (!/^[a-fA-F0-9]{32}$/.test(projectId.trim())) {
      setMessage('A project ID must be 32 hexadecimal characters. This is not a wallet key.'); return
    }
    const id = ++attempt.current
    setBusy(true); setQr(''); setAccounts([]); setMessage('Preparing address-only pairing…')
    let client: SignClient | undefined
    let topic: string | undefined
    let pairingTopic: string | undefined
    let timeout: ReturnType<typeof setTimeout> | undefined
    const close = async () => {
      if (topic && client) { const closing = topic; topic = undefined; await client.disconnect({ topic: closing, reason: { code: 6000, message: 'Address-only lookup complete or cancelled' } }) }
      if (pairingTopic && client) { const closing = pairingTopic; pairingTopic = undefined; await client.core.pairing.disconnect({ topic: closing }) }
    }
    cleanup.current = async () => { try { await close() } catch { /* Local invalidation already prevents account adoption. */ } }
    timeout = setTimeout(() => {
      if (attempt.current !== id) return
      attempt.current++; setQr(''); setBusy(false); setMessage('Pairing timed out. Revoke any pending TradeSync pairing in your wallet before retrying.'); void cleanup.current?.()
    }, 120_000)
    try {
      const [{ default: Client }, { default: QRCode }] = await Promise.all([import('@walletconnect/sign-client'), import('qrcode')])
      if (attempt.current !== id) return
      client = await Client.init({
        projectId: projectId.trim(), logger: 'silent', storage: memoryStorage(), telemetryEnabled: false,
        metadata: { name: 'TradeSync — address only', description: 'Share an EVM public address. No signatures, transactions or execution.', url: window.location.origin, icons: [] },
      })
      if (attempt.current !== id) return
      const { uri, approval } = await client.connect({ requiredNamespaces: ADDRESS_ONLY_NAMESPACES })
      pairingTopic = uri?.split(':')[1]?.split('@')[0]
      // Attach immediately so rejection cannot become an unhandled promise while QR renders.
      const approved = approval().then((value) => ({ value }), () => ({ value: null }))
      if (uri && attempt.current === id) {
        const image = await QRCode.toDataURL(uri, { width: 280, margin: 2 })
        if (attempt.current === id) { setQr(image); setMessage('Scan with a compatible WalletConnect EVM wallet. Approve address sharing only; never approve a signature here.') }
      }
      const { value: session } = await approved
      if (!session) throw new Error('Pairing rejected')
      topic = session.topic
      const shared = publicAddresses(session.namespaces)
      await close()
      if (attempt.current === id) { setAccounts(shared); setQr(''); setMessage('Address sharing completed; session closed. Choose an address to inspect on Hyperliquid. No ownership proof or trading authority was granted.') }
    } catch {
      if (attempt.current === id) { setQr(''); setMessage('Pairing could not complete safely. Check the project ID, relay access and wallet support for address-only sessions. No account was adopted. Revoke a remaining TradeSync session in your wallet if shown.') }
    } finally {
      clearTimeout(timeout)
      try { await close() } catch { /* Never adopt an address after a failed close. */ }
      try { await client?.core.relayer.transportClose() } catch { /* Do not reconnect merely for cleanup. */ }
      if (attempt.current === id) setBusy(false)
    }
  }

  return <div className="border border-slate-700 rounded p-4 mb-5">
    <h3>Pair a wallet by QR</h3>
    <p className="metric-sub">Optional WalletConnect connection — no browser extension required. Uses an Ethereum-format address for identity only; it does not select a Hyperliquid trading network. Phantom support is not assumed.</p>
    <label>Public WalletConnect project ID<input aria-label="Public WalletConnect project ID" value={projectId} disabled={busy} maxLength={32} autoComplete="off" spellCheck={false} onChange={(event) => setProjectId(event.target.value)} className="w-full bg-slate-900 border border-slate-700 rounded p-2 mt-2" /></label>
    <div className="flex gap-3 flex-wrap mt-3">
      <button type="button" className="chip" disabled={busy || !/^[a-fA-F0-9]{32}$/.test(projectId.trim())} onClick={() => void pair()}>Pair wallet — address only</button>
      <button type="button" className="chip" onClick={() => { attempt.current++; setQr(''); setAccounts([]); setBusy(false); setMessage('Cleared locally. If your wallet still lists a TradeSync pairing, revoke it there.'); void cleanup.current?.() }}>Cancel / clear pairing</button>
      <a href="https://dashboard.reown.com" target="_blank" rel="noopener noreferrer" className="text-blue-400">Project setup</a>
    </div>
    <p role="status" className="mt-3">{message}</p>
    {qr && <><img src={qr} alt="Private, short-lived WalletConnect pairing QR" width={280} height={280} style={{ maxWidth: '100%' }} /><p className="metric-sub">Do not share or screenshot this QR. It expires from this panel after two minutes.</p></>}
    {accounts.map((address) => <button key={address} type="button" className="chip mt-2" style={{ overflowWrap: 'anywhere', whiteSpace: 'normal' }} onClick={() => onAddress(address)}>Watch {address}</button>)}
    <p className="metric-sub mt-3">Pairing uses an external relay and its licence/usage terms. Session material stays in memory. No seed phrase, private key, signing methods, analytics UI or paid upgrade is requested. Import a wallet only in its own trusted application.</p>
    <small>Portions © 2025 Reown, Inc. All Rights Reserved. <a href="/walletconnect-license.txt" target="_blank" rel="noopener noreferrer">WalletConnect Community License</a></small>
  </div>
}
