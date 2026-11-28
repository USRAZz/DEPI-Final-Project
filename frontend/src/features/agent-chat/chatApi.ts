// Owner: Yossra. POST /api/chat: the api checks the session and forwards to services/agent /v1/chat with the user's
// own id and role (services/api/app/assistant.py). Shapes = securefin_contracts ChatRequest / ChatResponse.
// VITE_CHAT_URL overrides the address.

export type RiskLevel = 'low' | 'medium' | 'high'

export interface ChatTurn {
  role: 'user' | 'assistant'
  content: string
}

export interface RiskReason {
  code: string
  text: string
}

export interface InvoiceAlert {
  invoice_id: number
  invoice_number: string | null
  vendor: string | null
  status: string | null
  level: RiskLevel | null
  score: number | null
  reasons: RiskReason[]
}

export interface ProposedAction {
  tool: 'create_payment_request'
  params: { invoice_id: number; vendor_id: number; amount: string; currency: string }
  rationale: string
}

export interface ChatResponse {
  answer: string
  proposed_actions: ProposedAction[]
  alerts: InvoiceAlert[]
  sources: string[]
}

export interface Caller {
  id: number
  role: string
}

const CHAT_URL = (import.meta.env.VITE_CHAT_URL as string | undefined) ?? '/api/chat'
const MAX_HISTORY = 10 // the agent uses the last 10 turns

// The agent adds the alert reasons as text under the answer for plain clients (services/agent/app/alerts.py).
// This page shows them as cards instead, so the text block is cut off here.
const ALERT_BLOCK_TITLES = ['\n\nWhy these invoices have alerts:', '\n\nسبب التنبيهات:']

export function answerWithoutAlertBlock(answer: string): string {
  const at = Math.min(...ALERT_BLOCK_TITLES.map((title) => answer.indexOf(title)).filter((i) => i >= 0), answer.length)
  return answer.slice(0, at).trimEnd()
}

/** The signed-in user's identity for the api: the JWT when there is one, else the development login. */
export function identityHeaders(caller: Caller): Record<string, string> {
  let token: string | null = null
  try {
    token = localStorage.getItem('token')
  } catch {
    /* storage blocked */
  }
  return token ? { Authorization: `Bearer ${token}` } : { 'X-User-Id': String(caller.id) }
}

export async function sendChat(message: string, history: ChatTurn[], caller: Caller): Promise<ChatResponse> {
  // X-User-Id = the api's development login (replaced by the JWT); the api takes the role from the session
  const res = await fetch(CHAT_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...identityHeaders(caller) },
    body: JSON.stringify({ message, history: history.slice(-MAX_HISTORY) }),
  })
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`)
  const body = (await res.json()) as Partial<ChatResponse>
  return { answer: body.answer ?? '', proposed_actions: body.proposed_actions ?? [], alerts: body.alerts ?? [],
           sources: body.sources ?? [] }
}
