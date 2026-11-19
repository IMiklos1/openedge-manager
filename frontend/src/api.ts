export type Value = string | number | boolean
export type Values = Record<string, Value>

export interface Field {
  type: 'integer' | 'size' | 'duration' | 'choice' | 'boolean' | 'text' | 'attribute_regex'
  label?: string
  default?: Value
  min?: number
  max?: number
  choices?: string[]
  multiline?: boolean
}

export interface ProcessorSchema {
  description: string
  dynamic_properties: boolean
  properties: Record<string, Field>
  scheduling: Record<string, Field>
}

export type Catalog = Record<string, {
  category: string
  status: string
  configuration?: ProcessorSchema
}>

export interface Processor {
  id: string
  type: string
  label?: string | null
  description?: string | null
  position?: { x: number; y: number } | null
  config: Values
  scheduling?: Values
  attributes?: Record<string, string>
  auto_terminate_success?: boolean | null
}

export interface FlowConnection {
  id: string
  source: string
  target: string
  source_relationship: string
  label?: string | null
  queue?: Values
}

export interface Definition {
  schema_version: '1.0'
  flow_id: string
  name: string
  description?: string | null
  target_class?: string
  nodes: Processor[]
  connections: FlowConnection[]
  parameters?: Record<string, unknown>
}

export interface Agent {
  id: string
  hostname: string | null
  agent_class: string
  runtime: string | null
  runtime_version: string | null
  os_name: string | null
  architecture: string | null
  health: 'RECENT' | 'STALE' | 'UNKNOWN'
  last_seen: string | null
  can_deploy_flow: boolean
}

export interface Draft {
  id: string
  version: number
  validation_errors: string[]
}

export interface FlowSummary {
  id: string
  name: string
  version: number
  status: 'DRAFT' | 'PUBLISHED'
}

export interface StoredFlow extends Draft, FlowSummary {
  description: string | null
  definition: Definition
  published_sha256: string | null
}

export interface Revision {
  version: number
  name: string
  created_at: string
  sha256: string | null
}

export interface PublishedFlow {
  id: string
  version: number
  sha256: string
  runtime_version: string
}

export const deploymentStatuses = ['PENDING', 'DISPATCHED', 'ACKNOWLEDGED', 'APPLIED', 'FAILED'] as const

export interface Deployment {
  id: string
  flow_id: string
  flow_name?: string | null
  version: number
  status: typeof deploymentStatuses[number]
  agent_id: string | null
  target_class: string
  ack_state: string | null
  acknowledged_at: string | null
  applied_at: string | null
  created_at: string
  sha256: string | null
}

export const apiBase = import.meta.env.VITE_API_BASE_URL || ''

export async function apiRequest<T>(path: string, payload?: object, method = 'POST'): Promise<T> {
  const response = await fetch(`${apiBase}/api/v1${path}`, payload === undefined ? undefined : {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  const body = await response.json()
  if (!response.ok) {
    throw new Error(typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail ?? body))
  }
  return body as T
}
