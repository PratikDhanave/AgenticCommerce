import { useCallback, useEffect, useRef, useState } from 'react'
import type { Act, Decision, Item, Product, RunState, Terms } from './types'

const EMPTY: RunState = {
  status: 'idle', mode: 'replay', left: [], right: [], decisions: [],
}

let uid = 0
const nid = () => `i${++uid}`

/** Merchant-side chatter goes right, the buyer-facing lane goes left. */
function lane(agent: string): 'left' | 'right' {
  return agent === 'merchant_agent' ? 'right' : 'left'
}

export function useRun(
  session = 'demo',
  /** Raw event tap, used by the voice layer to speak turns as they open. */
  onEvent?: (e: any) => void,
) {
  const [state, setState] = useState<RunState>(EMPTY)
  const tap = useRef(onEvent)
  tap.current = onEvent
  const [acts, setActs] = useState<Act[]>([])
  const [liveAvailable, setLiveAvailable] = useState(false)
  const [terms, setTerms] = useState<Terms | null>(null)
  const [defaults, setDefaults] = useState<Terms | null>(null)
  const [materials, setMaterials] = useState<string[]>([])
  const [products, setProducts] = useState<Product[]>([])
  const es = useRef<EventSource | null>(null)

  useEffect(() => {
    fetch('/api/acts').then(r => r.json())
      .then(d => setActs(d.acts)).catch(() => {})
    fetch('/api/health').then(r => r.json())
      .then(d => setLiveAvailable(!!d.live_available)).catch(() => {})
    fetch('/api/catalog').then(r => r.json())
      .then(d => setProducts(d.items)).catch(() => {})
    fetch(`/api/mandate/terms?session=${session}`).then(r => r.json())
      .then(d => { setTerms(d.terms); setDefaults(d.defaults); setMaterials(d.materials) })
      .catch(() => {})
  }, [session])

  /** Grant the agent a new set of terms. Returns an error string, or null. */
  const saveTerms = useCallback(async (next: Terms): Promise<string | null> => {
    try {
      const r = await fetch(`/api/mandate/terms?session=${session}`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(next),
      })
      const d = await r.json()
      if (!r.ok) return d?.detail ?? 'Could not issue those terms.'
      setTerms(d.terms)
      setState(s => ({ ...s, mandate: d.mandate }))
      return null
    } catch {
      return 'Could not reach the server.'
    }
  }, [session])

  const stop = useCallback(() => {
    es.current?.close()
    es.current = null
    setState(s => (s.status === 'idle' ? s : { ...s, status: 'done' }))
  }, [])

  const reset = useCallback(() => {
    es.current?.close(); es.current = null
    setState(EMPTY)
  }, [])

  const approve = useCallback((ok: boolean) => {
    fetch(`/api/approve?session=${session}&approved=${ok}`, { method: 'POST' })
      .catch(() => {})
  }, [session])

  const run = useCallback((
    act: string, mode: 'replay' | 'live', voice = false,
  ) => {
    es.current?.close()
    setState({ ...EMPTY, status: 'running', mode, act })

    const src = new EventSource(
      `/api/stream?session=${session}&act=${act}&mode=${mode}&voice=${voice}`,
    )
    es.current = src

    src.onerror = () => {
      src.close(); es.current = null
      setState(s => s.status === 'running'
        ? { ...s, status: 'done', error: s.error ?? 'Stream closed.' }
        : s)
    }

    src.onmessage = (raw) => {
      const e = JSON.parse(raw.data) as any
      tap.current?.(e)
      setState(s => reduce(s, e))
    }
  }, [session])

  useEffect(() => () => es.current?.close(), [])

  return { state, acts, liveAvailable, run, stop, reset, approve,
           terms, defaults, materials, products, saveTerms }
}

function push(s: RunState, side: 'left' | 'right', item: Item): RunState {
  return side === 'left'
    ? { ...s, left: [...s.left, item] }
    : { ...s, right: [...s.right, item] }
}

/** Drop any trailing "thinking" placeholder for this agent. */
function unthink(list: Item[], agent: string): Item[] {
  return list.filter(i => !(i.k === 'thinking' && i.agent === agent))
}

function reduce(s: RunState, e: any): RunState {
  switch (e.kind) {
    case 'run_started':
      return { ...s, status: 'running', mode: e.mode, act: e.act,
               title: e.title, beat: e.beat, mandate: e.mandate }

    case 'user_message':
      return push(s, 'left', { k: 'human', id: nid(), text: e.text })

    case 'agent_thinking': {
      const side = lane(e.agent)
      return push(s, side, { k: 'thinking', id: nid(), agent: e.agent })
    }

    case 'agent_message_start': {
      const side = lane(e.agent)
      const list = unthink(side === 'left' ? s.left : s.right, e.agent)
      const item: Item = { k: 'agent', id: nid(), agent: e.agent, text: '', live: true }
      return side === 'left'
        ? { ...s, left: [...list, item] }
        : { ...s, right: [...list, item] }
    }

    case 'agent_token': {
      const side = lane(e.agent)
      const key = side === 'left' ? 'left' : 'right'
      const list = unthink(s[key], e.agent)
      // Append to the open bubble, or open one (live ADK streams without a start).
      const last = list[list.length - 1]
      if (last && last.k === 'agent' && last.agent === e.agent && last.live) {
        const next = [...list]
        next[next.length - 1] = { ...last, text: last.text + e.text }
        return { ...s, [key]: next } as RunState
      }
      return { ...s, [key]: [...list, {
        k: 'agent', id: nid(), agent: e.agent, text: e.text, live: true,
      }] } as RunState
    }

    case 'agent_message_end': {
      const key = lane(e.agent) === 'left' ? 'left' : 'right'
      const next = s[key].map(i =>
        i.k === 'agent' && i.live && i.agent === e.agent
          ? { ...i, text: e.text ?? i.text, live: false } : i)
      return { ...s, [key]: next } as RunState
    }

    case 'turn_boundary': {
      const key = lane(e.agent) === 'left' ? 'left' : 'right'
      return { ...s, [key]: s[key].map(i =>
        i.k === 'agent' && i.live ? { ...i, live: false } : i) } as RunState
    }

    case 'tool_call': {
      const side = lane(e.agent)
      const key = side === 'left' ? 'left' : 'right'
      const list = unthink(s[key], e.agent).map(i =>
        i.k === 'agent' && i.live ? { ...i, live: false } : i)
      return { ...s, [key]: [...list, {
        k: 'tool', id: e.call_id || nid(), agent: e.agent, tool: e.tool,
        args: e.args ?? {}, done: false,
      }] } as RunState
    }

    case 'tool_result': {
      const key = lane(e.agent) === 'left' ? 'left' : 'right'
      let hit = false
      const next = s[key].map(i => {
        if (!hit && i.k === 'tool' && i.tool === e.tool && !i.done) {
          hit = true
          return { ...i, result: e.result, done: true }
        }
        return i
      })
      return { ...s, [key]: next, mandate: e.mandate ?? s.mandate } as RunState
    }

    case 'a2a_message':
      return push(s, 'right', {
        k: 'a2a', id: nid(), frm: e.frm, to: e.to, text: e.text })

    case 'catalog_search':
      return push(s, 'right', {
        k: 'cards', id: nid(),
        label: `${e.count} match the buyer's constraints`,
        items: e.items as Product[] })

    case 'product_lookup':
      return push(s, 'right', {
        k: 'cards', id: nid(), label: 'Live stock lookup',
        items: [e.item as Product],
        dead: (e.item as Product).stock === 0 ? e.item.sku : undefined })

    case 'alternatives_offered':
      return push(s, 'right', {
        k: 'cards', id: nid(),
        label: `In-stock alternatives for ${e.for_sku}`,
        items: e.alternatives as Product[] })

    case 'mandate_read':
      return { ...s, mandate: e.mandate }

    case 'mandate_decision': {
      const d: Decision = {
        sku: e.sku, title: e.title, amount: e.amount, allowed: e.allowed,
        code: e.code, reason: e.reason, checks: e.checks ?? [],
      }
      return { ...s, mandate: e.mandate ?? s.mandate,
               decisions: [...s.decisions, d] }
    }

    case 'approval_required':
      return { ...s, status: 'awaiting_human', mandate: e.mandate ?? s.mandate,
               approval: { sku: e.sku, title: e.title, amount: e.amount,
                           reason: e.reason }, approvalResolved: false }

    case 'approval_resolved':
      return { ...s, status: 'running', approvalResolved: true,
               approval: e.approved ? s.approval : undefined }

    case 'payment_settled':
      return { ...s, receipt: e.receipt, mandate: e.mandate ?? s.mandate,
               approval: undefined }

    case 'payment_refused': {
      const d: Decision = {
        sku: e.sku, title: e.title, amount: e.amount, allowed: false,
        code: e.code, reason: e.reason, checks: e.checks ?? [],
      }
      return { ...s, blocked: d, mandate: e.mandate ?? s.mandate,
               decisions: [...s.decisions, d] }
    }

    case 'run_finished': {
      const blocked = e.status === 'blocked_by_mandate'
        ? (s.blocked ?? [...s.decisions].reverse().find(d => !d.allowed))
        : s.blocked
      return { ...s, status: 'done', finish: e.status,
               mandate: e.mandate ?? s.mandate, blocked,
               left: s.left.map(i => i.k === 'agent' ? { ...i, live: false } : i),
               right: s.right.map(i => i.k === 'agent' ? { ...i, live: false } : i) }
    }

    case 'error':
      return { ...s, error: `${e.message}${e.hint ? ' — ' + e.hint : ''}` }

    default:
      return s
  }
}
