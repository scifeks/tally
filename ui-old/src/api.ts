import { reactive } from 'vue'
import axios from 'axios'

export interface Finding {
  id: number
  id_fingerprint: string | null
  run_id: number | null
  tool: string
  domain: string | null
  segment: string | null
  repo: string | null
  finding_type: string[]
  severity: string | null
  confidence: string | null
  file: string | null
  rule_id: string | null
  url: string | null
  host: string | null
  port: string | null
  vulnerability_id: string | null
  package_name: string | null
  ecosystem: string | null
  description: string | null
  package_version: string | null
  cwe: string[]
  enriched: number | null
  meta: Record<string, unknown>
  first_seen: string | null
  last_seen: string | null
  seen_count: number | null
  status: string | null
  triaged_at: string | null
  triaged_by: string | null
  should_report: number
  business_impact: string | null
  tal_id: string | null
}

export interface FindingPatch {
  severity?: string
  confidence?: string
  finding_type?: string[]
  description?: string
  status?: string
  should_report?: boolean
  business_impact?: string
  tal_id?: string
  cwe?: string[]
  meta_remediation?: string
  meta_risk_type?: string
  meta_owasp_name?: string
  meta_title?: string
  meta_tags?: string[]
}

export const authStore = reactive({
  token: null as string | null,
  initialised: false,
})

const http = axios.create()

http.interceptors.request.use((config) => {
  if (authStore.token) {
    config.headers.Authorization = `Bearer ${authStore.token}`
  }
  return config
})

export function initToken(): boolean {
  const params = new URLSearchParams(window.location.search)
  const token = params.get('token')
  if (!token) return false
  authStore.token = token
  authStore.initialised = true
  window.history.replaceState({}, '', '/')
  return true
}

export async function getFindings(params?: {
  tool?: string
  domain?: string
  status?: string
  segment?: string
  visualize_only?: boolean
}): Promise<Finding[]> {
  const response = await http.get<Finding[]>('/api/findings/', { params })
  return response.data
}

export async function getFinding(id: number): Promise<Finding> {
  const response = await http.get<Finding>(`/api/findings/${id}`)
  return response.data
}

export async function patchFinding(id: number, patch: FindingPatch): Promise<Finding> {
  const response = await http.patch<Finding>(`/api/findings/${id}`, patch)
  return response.data
}

export interface BatchFindingPatch {
  ids: number[]
  should_report?: boolean
  status?: string
  severity?: string
  confidence?: string
  description?: string
  business_impact?: string
  tal_id?: string
}

export async function batchPatchFindings(
  body: BatchFindingPatch,
): Promise<{ updated: number }> {
  const response = await http.patch<{ updated: number }>('/api/findings/batch', body)
  return response.data
}

export interface FieldSpec {
  editor: 'select' | 'text' | 'boolean' | 'tags'
  options?: string[]
}

export interface AppConfig {
  editable_fields: Record<string, FieldSpec>
}

export async function getConfig(): Promise<AppConfig> {
  const response = await http.get<AppConfig>('/api/config/')
  return response.data
}
