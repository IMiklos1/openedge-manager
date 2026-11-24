export const runtimeLabels = { 'minifi-java': 'MiNiFi Java', 'minifi-cpp': 'MiNiFi C++' } as const
export type Runtime = keyof typeof runtimeLabels

export type Value = string | number | boolean
export type Values = Record<string, Value>

export interface Field {
  type: 'integer' | 'size' | 'duration' | 'choice' | 'boolean' | 'text' | 'attribute_regex' | 'service'
  label?: string
  default?: Value
  min?: number
  max?: number
  choices?: string[]
  multiline?: boolean
  description?: string
  required?: boolean
  sensitive?: boolean
  expression_scope?: string
  service?: string
  choice_labels?: Record<string, string>
  dependencies?: Record<string, string[]>
  modifies_classpath?: boolean
}

export interface ComponentSchema {
  description: string
  type: string
  bundle: { group: string; artifact: string; version: string }
  tags: string[]
  dynamic_properties: boolean
  dynamic?: { name: string; description: string; value: string; expressionLanguageScope: string }[]
  properties: Record<string, Field>
}

export interface ProcessorSchema extends ComponentSchema {
  inputRequirement?: 'INPUT_REQUIRED' | 'INPUT_ALLOWED' | 'INPUT_FORBIDDEN'
  relationships: Record<string, { description?: string }>
  dynamicRelationship?: { name: string; description: string }
  scheduling: Record<string, Field>
}

export interface ServiceSchema extends ComponentSchema {
  apis: { className: string }[]
}

export interface FlowEditor {
  queue: Record<string, Field>
  controller_services: Record<string, ServiceSchema>
}

export interface ControllerService {
  id: string
  type: string
  label?: string | null
  description?: string | null
  state?: 'ENABLED' | 'DISABLED'
  config: Values
  attributes?: Record<string, string>
}

export function sourceRelationships(node: Processor, schema: ProcessorSchema | undefined) {
  if (!schema) return []
  const fixed = Object.keys(schema.relationships)
  if (node.type === 'DistributeLoad') {
    const value = String(node.config['Number of Relationships'] ?? schema.properties['Number of Relationships'].default)
    if (/^[0-9]{1,3}$/.test(value)) return Array.from({ length: Number(value) }, (_, index) => String(index + 1))
  }
  const strategy = node.config['Routing Strategy']
  if (node.type === 'RouteOnAttribute' && strategy && strategy !== 'Route to Property name') return [...fixed, 'matched']
  if (node.type === 'RouteText' && strategy && strategy !== 'Route to each matching Property Name') return [...fixed, 'matched']
  return schema.dynamicRelationship ? [...new Set([...fixed, ...Object.keys(node.attributes ?? {})])] : fixed
}


export type Catalog = Record<string, {
  category: string
  status: string
  configuration?: ProcessorSchema
}>

export const remoteProcessGroup = 'RemoteProcessGroup'

export interface InputPort {
  id: string
  name: string
}

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
  auto_terminate?: string[] | null
  retry_relationships?: string[]
  target_port_id?: string | null
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
  runtime?: Runtime
  flow_id: string
  name: string
  description?: string | null
  target_class?: string
  nodes: Processor[]
  connections: FlowConnection[]
  controller_services?: ControllerService[]
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
  deployment_blocker: 'NOT_ENABLED' | 'INCOMPATIBLE_RUNTIME' | 'AWAITING_MANIFEST' | null
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
  runtime: Runtime
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
