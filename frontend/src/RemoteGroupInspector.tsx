import { useEffect, useState } from 'react'
import { apiRequest, type InputPort, type Processor } from './api'

export function RemoteGroupInspector({ node, onChange, disabled, errors }: {
  node: Processor
  onChange: (node: Processor) => void
  disabled: boolean
  errors: string[]
}) {
  const [attempt, setAttempt] = useState(0)
  const [result, setResult] = useState<{ ports?: InputPort[]; error?: string }>()
  useEffect(() => {
    let active = true
    setResult(undefined)
    apiRequest<InputPort[]>('/nifi/input-ports')
      .then(ports => { if (active) setResult({ ports }) })
      .catch(error => { if (active) setResult({ error: error.message }) })
    return () => { active = false }
  }, [attempt])
  const selected = node.target_port_id
  const ports = result?.ports ?? []
  return <aside className="inspector">
    <div className="inspector-title"><h2>Remote Process Group</h2></div>
    <div className="inspector-content">
      <label className="input-field">Group name<input value={node.label ?? ''} disabled={disabled}
        onChange={event => onChange({ ...node, label: event.target.value })}/></label>
      <label className="input-field">NiFi Input Port
        <select aria-label="NiFi Input Port" value={selected ?? ''} disabled={disabled || !result?.ports}
          onChange={event => onChange({ ...node, target_port_id: event.target.value || null })}>
          <option value="">Select an Input Port</option>
          {selected && !ports.some(port => port.id === selected) &&
            <option value={selected}>Saved port · {selected}</option>}
          {ports.map(port => <option value={port.id} key={port.id}>{port.name} · {port.id}</option>)}
        </select>
      </label>
      {selected && <code className="port-id">{selected}</code>}
      {!result && <p role="status">Loading Input Ports…</p>}
      {result?.error && <p role="alert">{result.error}</p>}
      {result?.ports?.length === 0 && <p>No Site-to-Site Input Ports. Create a port with remote access in NiFi.</p>}
      <button onClick={() => setAttempt(value => value + 1)}>Refresh Input Ports</button>
      {errors.map(error => <p key={error} role="alert">{error}</p>)}
    </div>
  </aside>
}
