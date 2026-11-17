import { useCallback, useState } from 'react'
import {
  ReactFlow, Background, Controls, MiniMap, addEdge, useNodesState, useEdgesState,
  type Connection, type Node
} from '@xyflow/react'
import { Activity, Boxes, GitBranch, Server, Workflow } from 'lucide-react'

const initialNodes: Node[] = [
  { id: 'n1', position: { x: 80, y: 100 }, data: { label: 'GetFile' }, type: 'input' },
  { id: 'n2', position: { x: 340, y: 100 }, data: { label: 'RouteOnAttribute' } },
  { id: 'n3', position: { x: 620, y: 100 }, data: { label: 'PublishMQTT' }, type: 'output' }
]
const initialEdges = [
  { id: 'e1-2', source: 'n1', target: 'n2', label: 'success' },
  { id: 'e2-3', source: 'n2', target: 'n3', label: 'matched' }
]
const api = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

export default function App() {
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges)
  const [tab, setTab] = useState('designer')
  const [status, setStatus] = useState('Local editor demo')
  const onConnect = useCallback((connection: Connection) => setEdges((eds) => addEdge(connection, eds)), [setEdges])
  const addProcessor = (type: string) => {
    const id = `node-${Date.now()}`
    setNodes((ns) => [...ns, { id, position: { x: 160 + ns.length * 35, y: 250 + (ns.length % 3) * 35 }, data: { label: type } }])
  }
  const saveDraft = async () => {
    const definition = {
      schema_version: '1.0', flow_id: 'demo-flow', name: 'Demo Edge Flow',
      target_class: 'unassigned',
      nodes: nodes.map(n => ({ id: n.id, type: String(n.data.label), config: {} })),
      connections: edges.map(e => ({ id: e.id, source: e.source, target: e.target, source_relationship: String(e.label || 'success') }))
    }
    try {
      const response = await fetch(`${api}/api/v1/flows`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: 'demo-flow', name: 'Demo Edge Flow', definition })
      })
      const body = await response.json()
      setStatus(response.ok ? `Saved ${body.id}; validation issues: ${body.validation_errors?.length ?? 0}` : JSON.stringify(body))
    } catch { setStatus('API unavailable. Start Docker Compose.') }
  }
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
          {['GetFile','TailFile','InvokeHTTP','PublishMQTT','ListenTCP','RouteOnAttribute'].map(x => <button key={x} onClick={() => addProcessor(x)}>{x}</button>)}
        </div><button className="primary" onClick={saveDraft}>Save draft</button></div>
        <div className="canvas"><ReactFlow nodes={nodes} edges={edges} onNodesChange={onNodesChange} onEdgesChange={onEdgesChange} onConnect={onConnect} fitView><Background/><MiniMap/><Controls/></ReactFlow></div>
        <div className="statusbar"><span className="dot"/> {status}<span className="spacer"/> {nodes.length} processors · {edges.length} connections</div>
      </> : <section className="placeholder"><div className="placeholdericon"><Server/></div><h2>{tab === 'agents' ? 'Agent inventory API foundation' : 'Deployment lifecycle foundation'}</h2><p>Inspect the starter API and schemas through the interactive documentation.</p><a href={`${api}/docs`} target="_blank" rel="noreferrer">Open API documentation ↗</a></section>}
    </main>
  </div>
}
