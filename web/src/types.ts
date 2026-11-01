export type AgentName = 'shopper_agent' | 'merchant_agent'

export interface Product {
  sku: string; title: string; price: number; material: string
  category: string; stock: number; delivery_days: number; rating: number
}

export interface Check { name: string; passed: boolean; detail: string }

export interface AuditEntry {
  seq: number; at: number; actor: string
  action: string; detail: string; code: string
}

export interface MandateState {
  mandate_id: string; issued_by: string; issued_to: string
  currency: string; total_budget: number; per_txn_cap: number
  auto_approve_below: number; excluded_materials: string[]
  max_delivery_days: number; spent: number; remaining: number
  expired: boolean; expires_in: number; audit: AuditEntry[]
}

export interface Receipt {
  receipt_id: string; mandate_id: string; sku: string; title: string
  amount: number; currency: string; at: number
  remaining_after: number; signature: string
}

export interface Decision {
  sku?: string; title?: string; amount?: number
  allowed: boolean; code: string; reason: string; checks: Check[]
}

export interface Approval {
  sku: string; title: string; amount: number; reason: string
}

/** One entry in a conversation lane. */
export type Item =
  | { k: 'human'; id: string; text: string }
  | { k: 'agent'; id: string; agent: AgentName; text: string; live: boolean }
  | { k: 'thinking'; id: string; agent: AgentName }
  | { k: 'tool'; id: string; agent: AgentName; tool: string
      args: Record<string, unknown>; result?: unknown; done: boolean }
  | { k: 'a2a'; id: string; frm: string; to: string; text: string }
  | { k: 'cards'; id: string; label: string; items: Product[]
      highlight?: string }

export interface Act {
  id: string; title: string; beat: string; prompt: string
  /** The SKU this act hinges on, used to preview what the terms would do. */
  focus?: string
}

/** The terms a human grants the agent. Editable before a run. */
export interface Terms {
  total_budget: number
  per_txn_cap: number
  auto_approve_below: number
  max_delivery_days: number
  excluded_materials: string[]
}

export type RunStatus = 'idle' | 'running' | 'awaiting_human' | 'done'

export interface RunState {
  status: RunStatus
  mode: 'replay' | 'live'
  act?: string
  title?: string
  beat?: string
  left: Item[]
  right: Item[]
  mandate?: MandateState
  decisions: Decision[]
  approval?: Approval
  approvalResolved?: boolean
  receipt?: Receipt
  blocked?: Decision
  finish?: string
  error?: string
}
