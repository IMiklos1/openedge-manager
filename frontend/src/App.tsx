import { useCallback, useEffect, useState } from 'react'
import {
  ReactFlow, Background, Controls, MiniMap, addEdge, useNodesState, useEdgesState,
  type Connection, type Node
} from '@xyflow/react'
import { Activity, Boxes, GitBranch, Server, Workflow } from 'lucide-react'
import { apiBase, apiRequest, type Agent, type Deployment, type Draft, type PublishedFlow } from './api'

const initialNodes: Node[] = [
  { id: 'n1', position: { x: 80, y: 100 }, data: { label: 'GetFile' }, type: 'input' },
  { id: 'n2', position: { x: 340, y: 100 }, data: { label: 'RouteOnAttribute' } },
  { id: 'n3', position: { x: 620, y: 100 }, data: { label: 'PublishMQTT' }, type: 'output' }
]
const initialEdges = [
  { id: 'e1-2', source: 'n1', target: 'n2', label: 'success' },
  { id: 'e2-3', source: 'n2', target: 'n3', label: 'matched' }
]
const demoNodes: Node[] = [
  { id: 'generate', position: { x: 100, y: 110 }, data: { label: 'GenerateFlowFile' } },
  { id: 'log', position: { x: 380, y: 110 }, data: { label: 'LogAttribute' } }
]
const demoEdges = [{ id: 'generated-file', source: 'generate', target: 'log', label: 'success' }]

export default function App() {
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges)
  const [tab, setTab] = useState('designer')
  const [name, setName] = useState('Demo Edge Flow')
  const [status, setStatus] = useState('Local editor demo')
  const [busy, setBusy] = useState(false)
  const [saved, setSaved] = useState<{ draft: Draft; snapshot: string }>()
  const [published, setPublished] = useState<PublishedFlow>()
  const [agents, setAgents] = useState<Agent[]>([])
  const [agentId, setAgentId] = useState('')
  const [deployment, setDeployment] = useState<Deployment>()
  const [agentError, setAgentError] = useState(false)
  const onConnect = useCallback((connection: Connection) => setEdges((current) => addEdge(connection, current)), [setEdges])
  const definition = {
    schema_version: '1.0', name,
    nodes: nodes.map(node => ({ id: node.id, type: String(node.data.label), config: {} })),
    connections: edges.map(edge => ({
      id: edge.id, source: edge.source, target: edge.target, source_relationship: String(edge.label || 'success'),
    })),
  }
  const snapshot = JSON.stringify(definition)
  const savedCurrent = saved?.snapshot === snapshot
  const activeDeployment = deployment && !['APPLIED', 'FAILED'].includes(deployment.status)
  const eligibleAgents = agents.filter(agent => agent.can_deploy_flow)

  useEffect(() => {
    let current = true
    const refresh = () => {
      apiRequest<Agent[]>('/agents').then(rows => {
        if (current) {
          setAgents(rows)
          setAgentError(false)
        }
      }).catch(() => { if (current) setAgentError(true) })
    }
    refresh()
    const timer = window.setInterval(refresh, 5000)
    return () => { current = false; window.clearInterval(timer) }
  }, [])

  const deploymentId = deployment?.id
  useEffect(() => {
    if (!deploymentId || !activeDeployment) return
    let current = true
    const timer = window.setInterval(async () => {
      try {
        const result = await apiRequest<Deployment>(`/deployments/${encodeURIComponent(deploymentId)}`)
        if (current) {
          setDeployment(result)
          setStatus(`Deployment ${result.status}${result.ack_state ? ` (${result.ack_state})` : ''}`)
        }
      } catch {
        if (current) setStatus('Could not refresh deployment. Retrying…')
      }
    }, 2500)
    return () => { current = false; window.clearInterval(timer) }
  }, [deploymentId, activeDeployment])

  const run = async (action: () => Promise<void>) => {
    setBusy(true)
    try {
      await action()
    } catch (error) {
      setStatus(error instanceof Error ? error.message : 'Request failed')
    } finally {
      setBusy(false)
    }
  }
  const addProcessor = (type: string) => {
    const id = crypto.randomUUID()
    setNodes(current => [...current, {
      id, position: { x: 160 + current.length * 35, y: 250 + (current.length % 3) * 35 }, data: { label: type },
    }])
  }
  const loadTestFlow = () => {
    if (nodes.length && !savedCurrent && !window.confirm('Replace the current canvas with the test flow?')) return
    setNodes(demoNodes)
    setEdges(demoEdges)
    setName('MiNiFi test flow')
    setSaved(undefined)
    setPublished(undefined)
    setStatus('Test flow loaded. Save a draft to continue.')
  }
  const saveDraft = () => run(async () => {
    const id = crypto.randomUUID()
    const draft = await apiRequest<Draft>('/flows', { id, name, definition: { ...definition, flow_id: id } })
    setSaved({ draft, snapshot })
    setPublished(undefined)
    setStatus(draft.validation_errors.length ? draft.validation_errors.join(' ') : `Draft saved (v${draft.version}).`)
  })
  const publishFlow = () => run(async () => {
    if (!savedCurrent || !saved) return
    const artifact = await apiRequest<PublishedFlow>(`/flows/${encodeURIComponent(saved.draft.id)}/publish`, {})
    setPublished(artifact)
    setStatus(`Published v${artifact.version} for MiNiFi Java ${artifact.runtime_version}.`)
  })
  const deployFlow = () => run(async () => {
    if (!published || !agentId || !savedCurrent) return
    const queued = await apiRequest<Deployment>('/deployments', { flow_id: published.id, agent_id: agentId })
    setDeployment(queued)
    setStatus(`Deployment ${queued.status}`)
  })

  return <div className="shell">
    <aside className="sidebar">
      <div className="brand"><div className="logo"><Workflow /></div><div><b>OpenEdge</b><small>MANAGER</small></div></div>
      <div className="navlabel">PLATFORM</div>
      <button className={tab === 'designer' ? 'nav active' : 'nav'} onClick={() => setTab('designer')}><GitBranch size={17}/> Flow Designer</button>
      <button className={tab === 'agents' ? 'nav active' : 'nav'} onClick={() => setTab('agents')}><Server size={17}/> Edge Agents</button>
      <button className={tab === 'deployments' ? 'nav active' : 'nav'} onClick={() => setTab('deployments')}><Boxes size={17}/> Deployments</button>
      <div className="sidebarbottom"><Activity size={15}/> Development preview</div>
    </aside>
    <main className="main">
      <header><div><span className="eyebrow">EDGE CONTROL PLANE / {tab.toUpperCase()}</span><h1>{tab === 'designer' ? 'Flow Designer' : tab === 'agents' ? 'Edge Agents' : 'Deployments'}</h1></div><div className="userpill">LOCAL · DEV</div></header>
      {tab === 'designer' ? <>
        <div className="toolbar"><div className="tools">
          {['GenerateFlowFile','LogAttribute','GetFile','TailFile','InvokeHTTP','PublishMQTT','ListenTCP','RouteOnAttribute'].map(x => <button key={x} onClick={() => addProcessor(x)}>{x}</button>)}
        </div></div>
        <div className="flow-actions">
          <button onClick={loadTestFlow} disabled={busy}>Load test flow</button>
          <label>Flow name <input value={name} maxLength={255} onChange={event => setName(event.target.value)}/></label>
          <button onClick={saveDraft} disabled={busy || !name.trim() || savedCurrent}>Save draft</button>
          <button onClick={publishFlow} disabled={busy || !savedCurrent || !!published}>Publish flow</button>
          <label>Test agent <select value={agentId} onChange={event => setAgentId(event.target.value)}>
            <option value="">{agentError ? 'Agent lookup failed' : eligibleAgents.length ? 'Select an agent' : 'No enabled test agent'}</option>
            {eligibleAgents.map(agent => <option key={agent.id} value={agent.id}>{agent.id}</option>)}
          </select></label>
          <button className="primary" onClick={deployFlow}
            disabled={busy || !published || !savedCurrent || !agentId || !!activeDeployment || !eligibleAgents.some(agent => agent.id === agentId)}>
            Deploy flow
          </button>
        </div>
        <div className="canvas"><ReactFlow nodes={nodes} edges={edges} onNodesChange={onNodesChange} onEdgesChange={onEdgesChange} onConnect={onConnect} fitView><Background/><MiniMap/><Controls/></ReactFlow></div>
        <div className="statusbar" role="status"><span className="dot"/> {status}<span className="spacer"/> {nodes.length} processors · {edges.length} connections</div>
      </> : <section className="placeholder"><div className="placeholdericon"><Server/></div><h2>{tab === 'agents' ? 'Agent inventory API foundation' : 'Deployment lifecycle foundation'}</h2><p>Inspect the starter API and schemas through the interactive documentation.</p><a href={`${apiBase}/docs`} target="_blank" rel="noreferrer">Open API documentation ↗</a></section>}
    </main>
  </div>
}
