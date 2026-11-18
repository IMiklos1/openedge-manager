export interface Agent {
  id: string
  can_deploy_flow: boolean
}

export interface Draft {
  id: string
  version: number
  validation_errors: string[]
}

export interface PublishedFlow {
  id: string
  version: number
  sha256: string
  runtime_version: string
}

export interface Deployment {
  id: string
  status: 'PENDING' | 'DISPATCHED' | 'ACKNOWLEDGED' | 'APPLIED' | 'FAILED'
  ack_state: string | null
}

export const apiBase = import.meta.env.VITE_API_BASE_URL || ''

export async function apiRequest<T>(path: string, payload?: object): Promise<T> {
  const response = await fetch(`${apiBase}/api/v1${path}`, payload === undefined ? undefined : {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  const body = await response.json()
  if (!response.ok) {
    throw new Error(typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail ?? body))
  }
  return body as T
}
