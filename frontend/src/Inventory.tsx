import { useEffect, useState } from 'react'
import { apiRequest, deploymentStatuses, type Agent, type Deployment } from './api'

export const pageSize = 25

export function Pagination({ offset, count, change }: { offset: number; count: number; change: (offset: number) => void }) {
  return <div className="pagination">
    <button disabled={offset === 0} onClick={() => change(offset - pageSize)}>Previous</button>
    <span>{count ? `${offset + 1}–${offset + count}` : '0'} shown</span>
    <button disabled={count < pageSize} onClick={() => change(offset + pageSize)}>Next</button>
  </div>
}

function useInventory<T>(path: string) {
  const [state, setState] = useState<{ path: string; rows: T[]; error?: string }>()
  useEffect(() => {
    let current = true
    const refresh = async () => {
      try {
        const rows = await apiRequest<T[]>(path)
        if (current) setState({ path, rows })
      } catch (error) {
        if (current) setState({ path, rows: [], error: error instanceof Error ? error.message : 'Request failed' })
      }
    }
    void refresh()
    const timer = window.setInterval(refresh, 5000)
    return () => { current = false; window.clearInterval(timer) }
  }, [path])
  return state?.path === path ? state : undefined
}

function formatTime(value: string | null) {
  return value ? new Date(value).toLocaleString() : '—'
}

export function AgentInventory({ showDeployments }: { showDeployments: (id: string) => void }) {
  const [query, setQuery] = useState('')
  const [agentClass, setAgentClass] = useState('')
  const [offset, setOffset] = useState(0)
  const groups = useInventory<{ name: string; agents: number; recent: number }>('/agent-classes?limit=12')
  const state = useInventory<Agent>(
    '/agents?' + new URLSearchParams({ q: query, agent_class: agentClass, offset: String(offset), limit: String(pageSize) }),
  )
  return <section className="records">
    {!!groups?.rows.length && <div className="class-list" aria-label="Agent class activity">{groups.rows.map(group =>
      <button onClick={() => { setAgentClass(group.name); setOffset(0) }} key={group.name}>
        <strong>{group.name}</strong><small>{group.recent} of {group.agents} checked in recently</small>
      </button>)}</div>}
    <div className="record-filters">
      <label className="input-field">Agent ID or hostname<input value={query} maxLength={128}
        onChange={event => { setQuery(event.target.value); setOffset(0) }}/></label>
      <label className="input-field">Agent class<input value={agentClass} maxLength={100}
        onChange={event => { setAgentClass(event.target.value); setOffset(0) }}/></label>
    </div>
    {!state ? <p className="muted">Loading agents…</p> : state.error ? <p role="alert">{state.error}</p>
      : state.rows.length === 0 ? <p className="muted">No matching agents have checked in.</p> :
      <div className="table-scroll"><table>
        <thead><tr><th>Agent</th><th>Class</th><th>Health</th><th>Runtime</th><th>Platform</th><th>Last seen</th><th>Deployments</th></tr></thead>
        <tbody>{state.rows.map(agent => <tr key={agent.id}>
          <td><strong>{agent.id}</strong><small>{agent.hostname ?? '—'}</small></td>
          <td>{agent.agent_class}</td><td><span className={`badge ${agent.health.toLowerCase()}`}>{agent.health}</span></td>
          <td>{agent.runtime} {agent.runtime_version}</td><td>{agent.os_name} {agent.architecture}</td><td>{formatTime(agent.last_seen)}</td>
          <td><button onClick={() => showDeployments(agent.id)}>View deployments</button></td>
        </tr>)}</tbody>
      </table></div>}
    <Pagination offset={offset} count={state?.rows.length ?? 0} change={setOffset}/>
  </section>
}

export function DeploymentInventory({ initialAgent }: { initialAgent: string }) {
  const [agent, setAgent] = useState(initialAgent)
  const [status, setStatus] = useState('')
  const [offset, setOffset] = useState(0)
  const state = useInventory<Deployment>(
    '/deployments?' + new URLSearchParams({ agent_id: agent, status, offset: String(offset), limit: String(pageSize) }),
  )
  return <section className="records">
    <div className="record-filters">
      <label className="input-field">Agent ID<input value={agent} maxLength={128}
        onChange={event => { setAgent(event.target.value); setOffset(0) }}/></label>
      <label className="input-field">Status<select aria-label="Status" value={status}
        onChange={event => { setStatus(event.target.value); setOffset(0) }}>
        <option value="">All statuses</option>{deploymentStatuses.map(value => <option key={value}>{value}</option>)}
      </select></label>
    </div>
    {!state ? <p className="muted">Loading deployments…</p> : state.error ? <p role="alert">{state.error}</p>
      : state.rows.length === 0 ? <p className="muted">No matching deployments.</p> :
      <div className="table-scroll"><table>
        <thead><tr><th>Flow</th><th>Target</th><th>Status</th><th>ACK</th><th>Queued</th><th>Applied</th></tr></thead>
        <tbody>{state.rows.map(deployment => <tr key={deployment.id}>
          <td><strong title={deployment.flow_id}>{deployment.flow_name ?? deployment.flow_id}</strong>
            <small>Version {deployment.version}</small></td>
          <td>{deployment.agent_id ?? deployment.target_class}{!deployment.agent_id && <small>Metadata only</small>}</td>
          <td><span className={`badge ${deployment.status.toLowerCase()}`}>{deployment.status}</span></td>
          <td>{deployment.ack_state ?? '—'}</td>
          <td>{formatTime(deployment.created_at)}</td><td>{formatTime(deployment.applied_at)}</td>
        </tr>)}</tbody>
      </table></div>}
    <Pagination offset={offset} count={state?.rows.length ?? 0} change={setOffset}/>
  </section>
}
