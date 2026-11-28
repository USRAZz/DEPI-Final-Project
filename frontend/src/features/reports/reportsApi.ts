// Owner: Karim. POST /api/reports: the api checks the session and forwards to services/agent /v1/reports
// (pattern ④ orchestrator-workers + evaluator-optimizer). Shapes = securefin_contracts Report.
import { identityHeaders, type Caller } from '../agent-chat/chatApi'

export type ReportQuality = 'passed' | 'numbers_checked' | 'fallback'

export interface ReportSection {
  key: string
  heading: string
  body: string
  facts: Record<string, unknown>
}

export interface Report {
  title: string
  language: 'ar' | 'en'
  date_from: string
  date_to: string
  summary: string
  sections: ReportSection[]
  rounds: number
  quality: ReportQuality
  notes: string[]
  models: Record<string, number>
  markdown: string
}

const REPORTS_URL = (import.meta.env.VITE_REPORTS_URL as string | undefined) ?? '/api/reports'

export async function requestReport(request: string, caller: Caller): Promise<Report> {
  const res = await fetch(REPORTS_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...identityHeaders(caller) },
    body: JSON.stringify({ request }),
  })
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`)
  return (await res.json()) as Report
}
