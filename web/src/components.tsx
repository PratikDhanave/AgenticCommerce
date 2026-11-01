import { useEffect, useRef, useState } from 'react'
import type {
  AgentName, Approval, AuditEntry, Decision, Item, MandateState, Product,
  Receipt, Terms,
} from './types'

export const inr = (n: number) => '₹' + n.toLocaleString('en-IN')

const LABEL: Record<string, string> = {
  shopper_agent: 'Shopper agent',
  merchant_agent: 'Merchant agent',
}

export function Avatar({ who }: { who: AgentName | 'human' | 'mandate' }) {
  const cls = who === 'merchant_agent' ? 'merchant'
    : who === 'human' ? 'human'
    : who === 'mandate' ? 'mandate' : 'shopper'
  const ch = who === 'merchant_agent' ? 'M'
    : who === 'human' ? 'P' : who === 'mandate' ? '§' : 'S'
  return <div className={`av ${cls}`} aria-hidden>{ch}</div>
}

/** Keeps a scroll container pinned to the bottom as events stream in.
 *  Pass enabled=false to hand scroll control to something else, e.g. the
 *  approval gate pinning itself into view. */
export function useAutoScroll(dep: unknown, enabled = true) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!enabled) return
    const el = ref.current
    if (el) el.scrollTop = el.scrollHeight
  }, [dep, enabled])
  return ref
}

function ToolChip({ item }: { item: Extract<Item, { k: 'tool' }> }) {
  const res = item.result as any
  const bad = res && (res.allowed === false || res.paid === false)
  const hold = res && res.code === 'NEEDS_HUMAN_APPROVAL'
  return (
    <details className="tool">
      <summary>
        {!item.done ? <span className="spin" />
          : bad ? <span className={hold ? 'dot-wait' : 'dot-bad'} />
          : <span className="dot-ok" />}
        <span className="tname">{item.tool}()</span>
        <span className="tsp" />
        <span className="chev">▶</span>
      </summary>
      <div className="guts">
        <p className="lbl">Arguments</p>
        <pre>{JSON.stringify(item.args, null, 2)}</pre>
        <p className="lbl">{item.done ? 'Returned' : 'Running…'}</p>
        {item.done && <pre>{JSON.stringify(item.result, null, 2)}</pre>}
      </div>
    </details>
  )
}

function Cards({ item }: { item: Extract<Item, { k: 'cards' }> }) {
  return (
    <>
      <div className="sect">{item.label}</div>
      <div className="cards">
        {item.items.map(p => (
          <div key={p.sku}
               className={`card${p.stock === 0 ? ' dead' : ''}`
                 + (item.highlight === p.sku ? ' pick' : '')}>
            <div style={{ minWidth: 0 }}>
              <div className="nm">{p.title}</div>
              <div className="mt">
                <span className="sku">{p.sku}</span>
                {' · '}{p.material}{' · '}{p.delivery_days}d
                {' · '}
                {p.stock === 0
                  ? <span className="tag oos">out of stock</span>
                  : <span className="tag ok">{p.stock} in stock</span>}
              </div>
            </div>
            <div className="pr">{inr(p.price)}</div>
          </div>
        ))}
      </div>
    </>
  )
}

export function Lane({ items }: { items: Item[] }) {
  return (
    <>
      {items.map(it => {
        switch (it.k) {
          case 'human':
            return (
              <div key={it.id} className="msg human">
                <Avatar who="human" />
                <div className="body">
                  <div className="who">Priya · buyer</div>
                  <div className="txt">{it.text}</div>
                </div>
              </div>
            )
          case 'thinking':
            return (
              <div key={it.id} className="msg">
                <Avatar who={it.agent} />
                <div className="body">
                  <div className="who">{LABEL[it.agent]}</div>
                  <div className="typing"><i /><i /><i /></div>
                </div>
              </div>
            )
          case 'agent':
            return (
              <div key={it.id} className="msg">
                <Avatar who={it.agent} />
                <div className="body">
                  <div className="who">{LABEL[it.agent]}</div>
                  <div className="txt">
                    {it.text}{it.live && <span className="caret" />}
                  </div>
                </div>
              </div>
            )
          case 'tool':
            return <ToolChip key={it.id} item={it} />
          case 'a2a':
            return (
              <div key={it.id}
                   className={`a2a ${it.frm === 'shopper_agent' ? 'out' : 'in'}`}>
                <div style={{ minWidth: 0 }}>
                  <div className="hop">
                    {it.frm} → {it.to}
                  </div>
                  <div className="pay">{it.text}</div>
                </div>
              </div>
            )
          case 'cards':
            return <Cards key={it.id} item={it} />
        }
      })}
    </>
  )
}

export function MandateCard(
  { m, onEdit, canEdit }:
  { m: MandateState; onEdit?: () => void; canEdit?: boolean },
) {
  const used = m.total_budget ? m.spent / m.total_budget : 0
  const cls = used >= 1 ? 'full' : used > 0.75 ? 'warn' : ''
  return (
    <div className="mcard">
      <h3>
        <Avatar who="mandate" /> Spending mandate
        {onEdit && (
          <button className="edit" onClick={onEdit} disabled={!canEdit}
                  title={canEdit ? 'Change what the agent is allowed to do (E)'
                                 : 'Stop the run to change the terms'}>
            Edit terms
          </button>
        )}
      </h3>
      <div className="id">{m.mandate_id}</div>

      <div className="meter">
        <div className="row">
          <span className="big">{inr(m.remaining)}</span>
          <span className="of">of {inr(m.total_budget)} left</span>
        </div>
        <div className={`bar ${cls}`}>
          <span style={{ width: `${Math.min(100, used * 100)}%` }} />
        </div>
      </div>

      <div className="limits">
        <div className="limit">
          <span className="k">Issued by</span>
          <span className="v">{m.issued_by}</span>
        </div>
        <div className="limit">
          <span className="k">Held by</span>
          <span className="v">{m.issued_to}</span>
        </div>
        <div className="limit">
          <span className="k">Per-transaction cap</span>
          <span className="v">{inr(m.per_txn_cap)}</span>
        </div>
        <div className="limit">
          <span className="k">Auto-approve below</span>
          <span className="v">{inr(m.auto_approve_below)}</span>
        </div>
        <div className="limit">
          <span className="k">Excluded materials</span>
          <span className="v">{m.excluded_materials.join(', ') || '—'}</span>
        </div>
        <div className="limit">
          <span className="k">Delivery window</span>
          <span className="v">≤ {m.max_delivery_days} days</span>
        </div>
      </div>
    </div>
  )
}

export function Verdict({ d, pin = false }: { d: Decision; pin?: boolean }) {
  const hold = d.code === 'NEEDS_HUMAN_APPROVAL'
  const cls = d.allowed ? 'allow' : hold ? 'hold' : 'block'
  const head = d.allowed ? 'Within mandate'
    : hold ? 'Human approval required' : 'Blocked by mandate'
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (pin) ref.current?.scrollIntoView({ block: 'start', behavior: 'smooth' })
  }, [pin, d.code, d.sku])
  return (
    <div className={`verdict ${cls}`} ref={ref}>
      <div className="vt">
        {head} <span className="code">{d.code}</span>
      </div>
      <div className="vr">
        {d.title && <strong>{d.title} · {inr(d.amount ?? 0)}</strong>}
        {d.title && <br />}
        {d.reason}
      </div>
    </div>
  )
}

export function Checks({ d }: { d: Decision }) {
  if (!d.checks.length) return null
  return (
    <>
      <div className="sect">Checks run · {d.sku}</div>
      <div className="checks">
        {d.checks.map((c, i) => (
          <div key={i} className={`check ${c.passed ? 'pass' : 'fail'}`}>
            <span className="ico">{c.passed ? '✓' : '✕'}</span>
            <span style={{ minWidth: 0 }}>
              <span className="nm">{c.name}</span>
              <br />
              <span className="dt">{c.detail}</span>
            </span>
          </div>
        ))}
      </div>
    </>
  )
}

export function Gate(
  { a, onApprove, onDeny, hint }:
  { a: Approval; onApprove: () => void; onDeny: () => void; hint?: string },
) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    ref.current?.scrollIntoView({ block: 'start', behavior: 'smooth' })
  }, [a.sku])
  return (
    <div className="gate" ref={ref}>
      <h4>⏸ Waiting on a human</h4>
      <div className="amt">{inr(a.amount)}</div>
      <div className="what">{a.title}</div>
      <div className="why">{a.reason}</div>
      <div className="row">
        <button className="btn btn-approve" onClick={onApprove}>
          Approve charge
        </button>
        <button className="btn btn-danger" onClick={onDeny}>Decline</button>
      </div>
      {hint && <div className="hint">{hint}</div>}
    </div>
  )
}

export function ReceiptCard({ r }: { r: Receipt }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    ref.current?.scrollIntoView({ block: 'start', behavior: 'smooth' })
  }, [r.receipt_id])
  return (
    <div className="receipt" ref={ref}>
      <h4>✓ Settled · signed receipt</h4>
      <div className="kv"><span className="k">Item</span>
        <span className="v">{r.title}</span></div>
      <div className="kv"><span className="k">SKU</span>
        <span className="v">{r.sku}</span></div>
      <div className="kv"><span className="k">Amount</span>
        <span className="v">{inr(r.amount)} {r.currency}</span></div>
      <div className="kv"><span className="k">Receipt</span>
        <span className="v">{r.receipt_id}</span></div>
      <div className="kv"><span className="k">Against mandate</span>
        <span className="v">{r.mandate_id}</span></div>
      <div className="kv"><span className="k">Budget left</span>
        <span className="v">{inr(r.remaining_after)}</span></div>
      <div className="sig">
        HMAC-SHA256 · verified<br />{r.signature}
      </div>
    </div>
  )
}

export function Audit({ entries }: { entries: AuditEntry[] }) {
  if (!entries.length) return null
  return (
    <>
      <div className="sect">Audit trail · append-only</div>
      <div className="audit">
        {entries.map(a => {
          const cls = a.code === 'OK' ? 'ok'
            : a.code === 'NEEDS_HUMAN_APPROVAL' ? 'hold' : 'bad'
          return (
            <div key={a.seq} className="aud">
              <span className="n">{String(a.seq).padStart(2, '0')}</span>
              <span className="ac">
                <b>{a.actor}</b> · {a.action}
                <br /><span className="dt">{a.detail}</span>
              </span>
              <span className={`cd ${cls}`}>{a.code}</span>
            </div>
          )
        })}
      </div>
    </>
  )
}

/* ---------------------------------------------------------------- mandate editor */

/** What these terms would do to one item, worked out client-side.
 *  Mirrors mandate.evaluate() so the human sees the consequence of the
 *  authority before granting it, not after the agent acts on it. */
function preview(t: Terms, p: Product): { code: string; label: string; tone: string } {
  if (p.stock <= 0)
    return { code: 'OUT_OF_STOCK', label: 'out of stock', tone: 'block' }
  if (t.excluded_materials.includes(p.material))
    return { code: 'MATERIAL_EXCLUDED', label: `${p.material} is excluded`, tone: 'block' }
  if (p.delivery_days > t.max_delivery_days)
    return { code: 'DELIVERY_TOO_SLOW', label: `${p.delivery_days}d exceeds your window`, tone: 'block' }
  if (p.price > t.per_txn_cap)
    return { code: 'EXCEEDS_TXN_CAP', label: 'over the per-transaction cap', tone: 'block' }
  if (p.price > t.total_budget)
    return { code: 'EXCEEDS_BUDGET', label: 'over the total budget', tone: 'block' }
  if (p.price > t.auto_approve_below)
    return { code: 'NEEDS_HUMAN_APPROVAL', label: 'would stop and ask you', tone: 'hold' }
  return { code: 'OK', label: 'agent would buy it without asking', tone: 'allow' }
}

const FIELDS: { key: keyof Terms; label: string; hint: string; step: number }[] = [
  { key: 'total_budget',      label: 'Total budget',      hint: 'across the whole mandate', step: 100 },
  { key: 'per_txn_cap',       label: 'Per-transaction cap', hint: 'the hard ceiling on any one purchase', step: 100 },
  { key: 'auto_approve_below', label: 'Ask me above',     hint: 'below this the agent acts alone', step: 100 },
]

export function MandateEditor(
  { terms, defaults, materials, focus, onSave, onCancel, busy }: {
    terms: Terms
    defaults: Terms | null
    materials: string[]
    focus?: Product
    onSave: (t: Terms) => Promise<string | null>
    onCancel: () => void
    busy: boolean
  },
) {
  const [draft, setDraft] = useState<Terms>(terms)
  const [err, setErr] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  // Mirror the server's coherence rules so the human is told immediately,
  // not after a round trip.
  const local =
    draft.per_txn_cap > draft.total_budget
      ? 'Cap is above the budget — the agent could never use the headroom.'
      : draft.auto_approve_below > draft.per_txn_cap
      ? 'Ask-me threshold is above the cap — nothing would ever pause for you.'
      : null

  const set = (k: keyof Terms, v: number) =>
    setDraft(d => ({ ...d, [k]: Math.max(0, v) }))

  const toggle = (m: string) =>
    setDraft(d => ({
      ...d,
      excluded_materials: d.excluded_materials.includes(m)
        ? d.excluded_materials.filter(x => x !== m)
        : [...d.excluded_materials, m],
    }))

  const save = async () => {
    if (local) { setErr(local); return }
    setSaving(true)
    const e = await onSave(draft)
    setSaving(false)
    setErr(e)
    if (!e) onCancel()
  }

  const pv = focus ? preview(draft, focus) : null
  const dirty = JSON.stringify(draft) !== JSON.stringify(terms)

  return (
    <div className="mcard editor">
      <h3><Avatar who="human" /> Grant authority</h3>
      <p className="lede">
        These are the terms the agent gets at the start of the next act.
        It cannot change them.
      </p>

      <div className="fields">
        {FIELDS.map(f => (
          <label key={f.key} className="field">
            <span className="fl">{f.label}</span>
            <span className="fh">{f.hint}</span>
            <span className="fin">
              <span className="cur">₹</span>
              <input type="number" min={0} step={f.step} disabled={busy}
                     value={draft[f.key] as number}
                     onChange={e => set(f.key, Number(e.target.value))} />
            </span>
          </label>
        ))}

        <label className="field">
          <span className="fl">Delivery window</span>
          <span className="fh">reject anything slower</span>
          <span className="fin">
            <input type="number" min={1} max={30} step={1} disabled={busy}
                   value={draft.max_delivery_days}
                   onChange={e => set('max_delivery_days', Number(e.target.value))} />
            <span className="cur suf">days</span>
          </span>
        </label>
      </div>

      <div className="sect">Materials the agent may not buy</div>
      <div className="chips">
        {materials.map(m => {
          const on = draft.excluded_materials.includes(m)
          return (
            <button key={m} type="button" disabled={busy}
                    className={`chip${on ? ' on' : ''}`}
                    aria-pressed={on} onClick={() => toggle(m)}>
              {m}
            </button>
          )
        })}
      </div>

      {pv && (
        <div className={`pv ${pv.tone}`}>
          <span className="pvl">On these terms</span>
          <span className="pvb">
            <strong>{focus!.title}</strong> at {inr(focus!.price)} — {pv.label}
          </span>
          <span className="code">{pv.code}</span>
        </div>
      )}

      {(err || local) && <div className="err">{err ?? local}</div>}

      <div className="erow">
        <button className="btn btn-primary" onClick={save}
                disabled={busy || saving || !!local || !dirty}>
          {saving ? 'Issuing…' : 'Issue mandate'}
        </button>
        <button className="btn btn-ghost" onClick={onCancel} disabled={saving}>
          Cancel
        </button>
        {defaults && (
          <button className="btn btn-ghost rst" disabled={busy || saving}
                  onClick={() => { setDraft(defaults); setErr(null) }}>
            Defaults
          </button>
        )}
      </div>
    </div>
  )
}
