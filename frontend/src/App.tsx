import { useEffect, useState } from 'react'
import {
  ReactFlow, Background, BackgroundVariant, Controls, MiniMap, useNodesState, useEdgesState,
  Handle, Position, type Connection, type Edge, type Node, type NodeProps,
} from '@xyflow/react'
import { Boxes, GitBranch, Plus, Server, Workflow, Cpu, Cable, Layers3 } from 'lucide-react'
import {
  apiBase, apiRequest, sourceRelationships, type Agent, type Catalog, type ControllerService, type Definition, type Deployment, type Draft, type FlowEditor,
  type FlowConnection, type FlowSummary, type Processor, type PublishedFlow, type Revision, type StoredFlow,
} from './api'
import { ConnectionInspector, ProcessorInspector, ServiceInspector } from './Inspector'
import { AgentInventory, DeploymentInventory, Pagination, pageSize } from './Inventory'

type GraphNode = Node<{ processor: Processor; inputForbidden?: boolean }, 'processor'>
type GraphEdge = Edge<{ connection: FlowConnection }>
type Selection = { kind: 'node' | 'edge' | 'service'; id: string }

function ProcessorCard({ data, selected }: NodeProps<GraphNode>) {
  const { processor } = data
  return <div className={`processor-card ${selected ? 'selected' : ''}`}>
    {!data.inputForbidden && processor.type !== 'GenerateFlowFile' && <Handle position={Position.Left} type="target"/>}
    <div className="processor-icon"><Cpu size={18}/></div>
    <div><strong>{processor.label || processor.type}</strong>
      <small>{processor.scheduling?.state === 'DISABLED' ? 'Disabled' : processor.type}</small></div>
    <Handle position={Position.Right} type="source"/>
  </div>
}

const nodeTypes = { processor: ProcessorCard }

function canvasNode(processor: Processor, index: number): GraphNode {
  return {
    id: processor.id, type: 'processor',
    position: processor.position ?? { x: 100 + (index % 3) * 270, y: 100 + Math.floor(index / 3) * 110 },
    ariaLabel: `Configure ${processor.label || processor.type}`,
    data: { processor },
  }
}

function canvasEdge(connection: FlowConnection): GraphEdge {
  return {
    id: connection.id, source: connection.source, target: connection.target,
    label: connection.label || connection.source_relationship,
    data: { connection },
  }
}

const emptyFlow: Definition = {
  schema_version: '1.0', flow_id: '', name: 'Untitled flow', description: null,
  target_class: 'unassigned', nodes: [], connections: [], parameters: {},
}
const testFlow: Definition = {
  ...emptyFlow, name: 'MiNiFi test flow',
  nodes: [
    { id: 'generate', type: 'GenerateFlowFile', config: {}, position: { x: 100, y: 160 } },
    { id: 'log', type: 'LogAttribute', config: {}, position: { x: 380, y: 160 } },
  ],
  connections: [{ id: 'generated-file', source: 'generate', target: 'log', source_relationship: 'success' }],
}

const navItems = [
  { id: 'designer', title: 'Flow Manager', icon: GitBranch },
  { id: 'agents', title: 'Edge Agents', icon: Server },
  { id: 'deployments', title: 'Deployments', icon: Boxes },
] as const

export default function App() {
  const [nodes, setNodes, onNodesChange] = useNodesState<GraphNode>([])
  const [edges, setEdges, onEdgesChange] = useEdgesState<GraphEdge>([])
  const [metadata, setMetadata] = useState<Definition>(emptyFlow)
  const [tab, setTab] = useState<typeof navItems[number]['id']>('designer')
  const [status, setStatus] = useState('')
  const [busy, setBusy] = useState(false)
  const [saved, setSaved] = useState<{ draft: Draft; snapshot: string; digest?: string }>()
  const [readOnly, setReadOnly] = useState(false)
  const [selection, setSelection] = useState<Selection>()
  const [catalog, setCatalog] = useState<Catalog>()
  const [editor, setEditor] = useState<FlowEditor>()
  const [serviceType, setServiceType] = useState('')
  const [wireSource, setWireSource] = useState('')
  const [wireTarget, setWireTarget] = useState('')
  const [catalogError, setCatalogError] = useState('')
  const [flows, setFlows] = useState<FlowSummary[]>()
  const [flowOffset, setFlowOffset] = useState(0)
  const [history, setHistory] = useState<Revision[]>([])
  const [catalogQuery, setCatalogQuery] = useState('')
  const [canvasKey, setCanvasKey] = useState(0)
  const [agents, setAgents] = useState<Agent[]>([])
  const [agentId, setAgentId] = useState('')
  const [deployments, setDeployments] = useState<Record<string, Deployment>>({})
  const [agentError, setAgentError] = useState(false)
  const [deploymentFilter, setDeploymentFilter] = useState('')

  const definition: Definition = {
    ...metadata,
    nodes: nodes.map(node => ({ ...node.data.processor, position: node.position })),
    connections: edges.map(edge => edge.data!.connection),
  }
  const snapshot = JSON.stringify(definition)
  const dirty = saved ? saved.snapshot !== snapshot : nodes.length > 0 || !!metadata.controller_services?.length || metadata.name !== emptyFlow.name || !!metadata.description
  const savedCurrent = saved && !dirty
  const deployment = deployments[agentId]
  const activeDeployment = deployment && !['APPLIED', 'FAILED'].includes(deployment.status)
  const eligibleAgents = agents.filter(agent => agent.can_deploy_flow)
  const node = selection?.kind === 'node' ? nodes.find(item => item.id === selection.id) : undefined
  const edge = selection?.kind === 'edge' ? edges.find(item => item.id === selection.id) : undefined
  const service = selection?.kind === 'service' ? metadata.controller_services?.find(item => item.id === selection.id) : undefined
  const serviceOptions = (metadata.controller_services ?? []).map(item => ({
    id: item.id, name: item.label || item.type, apis: editor?.controller_services[item.type]?.apis.map(api => api.className) ?? [],
  }))
  const errors = savedCurrent ? saved.draft.validation_errors : []
  const title = navItems.find(item => item.id === tab)?.title

  function relationshipsOf(id: string) {
    const source = nodes.find(item => item.id === id)?.data.processor
    return source ? sourceRelationships(source, catalog?.[source.type]?.configuration) : []
  }

  const onConnect = ({ source, target }: Pick<Connection, 'source' | 'target'>) => {
    if (!source || !target || !nodes.some(item => item.id === target) || !relationshipsOf(source).length) return
    if (nodes.find(item => item.id === target)?.data.inputForbidden) return
    const options = relationshipsOf(source)
    const preferred = options.includes('success') ? ['success', ...options.filter(item => item !== 'success')] : options
    const relationship = preferred.find(item => !edges.some(edge => edge.source === source && edge.target === target
      && edge.data?.connection.source_relationship === item))
    if (!relationship) return
    const id = crypto.randomUUID()
    const next = canvasEdge({ id, source, target, source_relationship: relationship })
    setEdges(current => [...current, next])
    setSelection({ kind: 'edge', id })
  }

  useEffect(() => {
    let current = true
    Promise.all([apiRequest<Catalog>('/catalog'), apiRequest<FlowEditor>('/flow-editor')])
      .then(([options, editor]) => {
        if (current) { setCatalog(options); setEditor(editor) }
      }).catch(error => { if (current) setCatalogError(error.message) })
    const refresh = () => apiRequest<Agent[]>('/agents?deployable=true').then(rows => {
      if (current) { setAgents(rows); setAgentError(false) }
    }).catch(() => { if (current) setAgentError(true) })
    void refresh()
    const timer = window.setInterval(refresh, 5000)
    return () => { current = false; window.clearInterval(timer) }
  }, [])

  const loadFlows = async (offset: number) => {
    const rows = await apiRequest<FlowSummary[]>(`/flows?offset=${offset}&limit=${pageSize}`)
    setFlows(rows)
  }
  useEffect(() => {
    let current = true
    setFlows(undefined)
    apiRequest<FlowSummary[]>(`/flows?offset=${flowOffset}&limit=${pageSize}`)
      .then(rows => { if (current) setFlows(rows) })
      .catch(error => { if (current) setStatus(error.message) })
    return () => { current = false }
  }, [flowOffset])

  useEffect(() => {
    if (!dirty) return
    const protect = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = '' }
    window.addEventListener('beforeunload', protect)
    return () => window.removeEventListener('beforeunload', protect)
  }, [dirty])

  const deploymentId = deployment?.id
  useEffect(() => {
    if (!deploymentId || !activeDeployment) return
    let current = true
    const timer = window.setInterval(async () => {
      try {
        const next = await apiRequest<Deployment>(`/deployments/${encodeURIComponent(deploymentId)}`)
        if (current && next.agent_id) setDeployments(previous => ({ ...previous, [next.agent_id!]: next }))
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

  function displayFlow(next: Definition, record?: StoredFlow, historical = false) {
    const nextNodes = next.nodes.map(graphNode)
    setMetadata(next)
    setNodes(nextNodes)
    setEdges(next.connections.map(canvasEdge))
    setSaved(record ? {
      draft: record,
      snapshot: JSON.stringify({ ...next, nodes: nextNodes.map(item => ({ ...item.data.processor, position: item.position })) }),
      digest: record.published_sha256 ?? undefined,
    } : undefined)
    setWireSource('')
    setWireTarget('')
    setReadOnly(historical)
    setSelection(undefined)
    setCanvasKey(current => current + 1)
  }

  const replace = (next: Definition) => {
    if (dirty && !window.confirm('Discard unsaved changes?')) return
    displayFlow(next)
    setHistory([])
    setStatus('')
  }

  const openFlow = (id: string, version?: number) => {
    if (dirty && !window.confirm('Discard unsaved changes?')) return
    void run(async () => {
      const path = `/flows/${encodeURIComponent(id)}`
      const [record, revisions] = await Promise.all([
        apiRequest<StoredFlow>(version === undefined ? path : `${path}/versions/${version}`),
        apiRequest<Revision[]>(`${path}/versions`),
      ])
      displayFlow(record.definition, record, version !== undefined)
      setHistory(revisions)
      setStatus('')
    })
  }

  function graphNode(processor: Processor, index: number) {
    const result = canvasNode(processor, index)
    result.data.inputForbidden = catalog?.[processor.type]?.configuration?.inputRequirement === 'INPUT_FORBIDDEN'
    return result
  }

  const addService = () => {
    if (!serviceType) return
    const next: ControllerService = { id: crypto.randomUUID(), type: serviceType, config: {} }
    setMetadata(current => ({ ...current, controller_services: [...(current.controller_services ?? []), next] }))
    setSelection({ kind: 'service', id: next.id })
    setServiceType('')
  }

  const addProcessor = (type: string) => {
    const processor: Processor = { id: crypto.randomUUID(), type, config: {} }
    setNodes(current => [...current, graphNode(processor, current.length)])
    setSelection({ kind: 'node', id: processor.id })
  }

  const saveDraft = () => run(async () => {
    const id = saved?.draft.id ?? crypto.randomUUID()
    const next = { ...definition, flow_id: id }
    const payload = { name: next.name, description: next.description, definition: next }
    const draft = saved
      ? await apiRequest<Draft>(`/flows/${encodeURIComponent(id)}`, { ...payload, expected_version: saved.draft.version }, 'PUT')
      : await apiRequest<Draft>('/flows', { ...payload, id })
    setMetadata(current => ({ ...current, flow_id: id }))
    setSaved({ draft, snapshot: JSON.stringify(next) })
    setStatus(`Draft saved (v${draft.version}).`)
    const revisions = await apiRequest<Revision[]>(`/flows/${encodeURIComponent(id)}/versions`)
    setHistory(revisions)
    await loadFlows(flowOffset)
  })

  const publishFlow = () => run(async () => {
    if (!savedCurrent || !saved) return
    const path = `/flows/${encodeURIComponent(saved.draft.id)}`
    const artifact = await apiRequest<PublishedFlow>(`${path}/publish?version=${saved.draft.version}`, {})
    setSaved({ ...saved, digest: artifact.sha256 })
    setStatus(`Published v${artifact.version} for MiNiFi Java ${artifact.runtime_version}.`)
    setHistory(await apiRequest<Revision[]>(`${path}/versions`))
    await loadFlows(flowOffset)
  })

  const deployFlow = () => run(async () => {
    if (!savedCurrent || !saved.digest || !agentId) return
    const queued = await apiRequest<Deployment>('/deployments', {
      flow_id: saved.draft.id, version: saved.draft.version, agent_id: agentId,
    })
    setDeployments(current => ({ ...current, [agentId]: queued }))
    setStatus('')
  })

  return <div className="app-shell">
    <header className="global-header">
      <div className="brand"><div className="logo"><Workflow size={22}/></div><div><b>OpenEdge</b><small>Manager</small></div></div>
      <nav aria-label="Workspace">{navItems.map(({ id, title, icon: Icon }) => <button key={id}
        className={tab === id ? 'active' : ''} aria-current={tab === id ? 'page' : undefined}
        onClick={() => { if (id === 'deployments') setDeploymentFilter(''); setTab(id) }}><Icon size={16}/>{title}</button>)}</nav>
      <a className="api-link" href={`${apiBase}/docs`} target="_blank" rel="noreferrer">API docs</a>
    </header>
    <main>
      <div className="page-heading"><h1>{title}</h1>{tab === 'designer' && <span className="runtime">MiNiFi Java</span>}</div>
      {tab === 'designer' && <div className="workspace">
        <aside className="library" aria-label="Flow library">
          <div className="library-heading"><Layers3 size={16}/><h2>Flows</h2><button className="icon-button" aria-label="New flow"
            disabled={busy} onClick={() => replace(emptyFlow)}><Plus size={17}/></button></div>
          <button className="template-button" disabled={busy} onClick={() => replace(testFlow)}>Load test flow</button>
          <div className="flow-list">
            {!flows ? <p className="muted">Loading flows…</p> : !flows.length ? <p className="muted">No saved flows.</p>
              : flows.map(flow => <button className={saved?.draft.id === flow.id ? 'current-flow' : ''} key={flow.id}
                type="button" disabled={busy} onClick={() => openFlow(flow.id)}>
                <strong>{flow.name}</strong><small>v{flow.version} · {flow.status === 'PUBLISHED' ? 'Published' : 'Draft'}</small>
              </button>)}
          </div>
          <Pagination count={flows?.length ?? 0} offset={flowOffset} change={setFlowOffset}/>
          {saved && <div className="revision-list"><h2>Versions</h2>
            {readOnly && <button disabled={busy} onClick={() => openFlow(saved.draft.id)}>Open latest</button>}
            {history.map(item => <button key={item.version} disabled={busy}
              className={saved.draft.version === item.version ? 'current-flow' : ''}
              onClick={() => openFlow(saved.draft.id, item.version)}>
              v{item.version} <small>{item.sha256 ? 'Published' : 'Draft'}</small>
            </button>)}</div>}
        </aside>
        <div className="editor">
          <div className="editor-bar">
            <label className="input-field flow-name">Flow name<input value={metadata.name} maxLength={255} disabled={readOnly}
              onChange={event => setMetadata({ ...metadata, name: event.target.value })}/></label>
            <button onClick={saveDraft} disabled={readOnly || busy || !metadata.name.trim() || !dirty}>Save draft</button>
            <button onClick={publishFlow} disabled={readOnly || busy || !savedCurrent || !!saved?.digest || errors.length > 0}>Publish flow</button>
            <label className="input-field">Target agent<select aria-label="Target agent" value={agentId} onChange={event => setAgentId(event.target.value)}>
              <option value="">{agentError ? 'Agent lookup failed' : eligibleAgents.length ? 'Select an agent' : 'No eligible agent'}</option>
              {eligibleAgents.map(agent => <option key={agent.id} value={agent.id}>{agent.id}{agent.health === 'STALE' ? ' (stale)' : ''}</option>)}
            </select></label>
            <button className="primary" onClick={deployFlow}
              disabled={busy || !savedCurrent || !saved?.digest || !eligibleAgents.some(agent => agent.id === agentId) || !!activeDeployment}>Deploy flow</button>
          </div>
          <div className="editor-message" role="status">
            <span>{status || (readOnly ? 'Saved version · read only' : dirty ? 'Unsaved changes' : saved?.digest ? 'Published' : '')}</span>
            {deployment && <span className={`badge ${deployment.status.toLowerCase()}`}>
              Deployment {deployment.status}{deployment.ack_state ? ` (${deployment.ack_state})` : ''}
            </span>}
          </div>
          <div className="editor-grid">
            <div className="graph-region">
              <div className="palette">
                <div className="palette-utilities">
                  <label>Processor palette<input type="search" value={catalogQuery} placeholder="Search processors"
                    onChange={event => setCatalogQuery(event.target.value)}/></label>
                  {edges.length > 0 && <select aria-label="Inspect connection"
                    value={selection?.kind === 'edge' ? selection.id : ''}
                    onChange={event => setSelection(event.target.value ? { kind: 'edge', id: event.target.value } : undefined)}>
                    <option value="">Inspect connection</option>
                    {edges.map(item => <option key={item.id} value={item.id}>
                      {item.data?.connection.label || item.data?.connection.source_relationship || 'Connection'}
                    </option>)}
                  </select>}
                </div>
                <div className="palette-options">
                  {catalogError && <p role="alert">{catalogError}</p>}
                  {!catalog && !catalogError && <span className="muted">Loading catalog…</span>}
                  {Object.entries(catalog ?? {}).filter(([kind, entry]) => [kind, ...(entry.configuration?.tags ?? [])]
                    .some(value => value.toLowerCase().includes(catalogQuery.toLowerCase())))
                    .map(([kind, item]) => <button key={kind} disabled={readOnly || busy} className={!item.configuration ? 'draft-option' : ''}
                      title={item.configuration ? item.category : 'Draft only in this runtime profile'}
                      onClick={() => addProcessor(kind)}>{kind}</button>)}
                </div>
                <div className="palette-utilities graph-controls">
                  {nodes.length > 1 && !readOnly && <div className="add-connection">
                    <select aria-label="Connection source" value={wireSource} onChange={event => setWireSource(event.target.value)}>
                      <option value="">Choose source</option>
                      {nodes.map(item => <option key={item.id} value={item.id}>{item.data.processor.label || item.data.processor.type}</option>)}
                    </select>
                    <select aria-label="Connection destination" value={wireTarget} onChange={event => setWireTarget(event.target.value)}>
                      <option value="">Choose destination</option>
                      {nodes.filter(item => !item.data.inputForbidden && item.id !== wireSource).map(item =>
                        <option key={item.id} value={item.id}>{item.data.processor.label || item.data.processor.type}</option>)}
                    </select>
                    <button disabled={!wireSource || !wireTarget || wireSource === wireTarget} onClick={() =>
                      onConnect({ source: wireSource, target: wireTarget })}>Add connection</button>
                  </div>}
                  {editor && <div className="add-connection">
                    <select aria-label="Controller service type" value={serviceType} disabled={readOnly || busy}
                      onChange={event => setServiceType(event.target.value)}>
                      <option value="">Controller service type</option>
                      {Object.keys(editor.controller_services).map(kind => <option key={kind}>{kind}</option>)}
                    </select>
                    <button onClick={addService} disabled={readOnly || busy || !serviceType}>Add service</button>
                    {!!serviceOptions.length && <select aria-label="Inspect controller service"
                      value={service?.id ?? ''} onChange={event => setSelection(event.target.value
                        ? { kind: 'service', id: event.target.value } : undefined)}>
                      <option value="">Inspect controller service</option>
                      {serviceOptions.map(item => <option value={item.id} key={item.id}>{item.name}</option>)}
                    </select>}
                  </div>}
                </div>
              </div>
              <div className="canvas">
                <ReactFlow key={canvasKey} nodeTypes={nodeTypes} nodes={nodes} edges={edges} fitView minZoom={0.25}
                  nodesDraggable={!readOnly} nodesConnectable={!readOnly} deleteKeyCode={readOnly ? null : 'Delete'}
                  onNodesChange={onNodesChange} onEdgesChange={onEdgesChange} onConnect={onConnect}
                  onNodeClick={(_, selected) => setSelection({ kind: 'node', id: selected.id })}
                  onEdgeClick={(_, selected) => setSelection({ kind: 'edge', id: selected.id })}
                  onPaneClick={() => setSelection(undefined)}>
                  <Background variant={BackgroundVariant.Dots} gap={20} size={1.4}/><MiniMap/><Controls/>
                </ReactFlow>
                <span className="canvas-count"><Cable size={14}/>{nodes.length} processors · {edges.length} connections</span>
              </div>
            </div>
            {node ? <ProcessorInspector key={node.id} node={node.data.processor}
              schema={catalog?.[node.data.processor.type]?.configuration} disabled={readOnly}
              services={serviceOptions} relationships={relationshipsOf(node.id)}
              connected={edges.filter(item => item.source === node.id).map(item => item.data!.connection.source_relationship)}
              errors={errors.filter(error => error.startsWith(`Node ${node.id}`) &&
                [',', ':'].includes(error[`Node ${node.id}`.length] ?? ''))}
              change={processor => setNodes(current => current.map(item => item.id === node.id
                ? { ...item, ariaLabel: `Configure ${processor.label || processor.type}`, data: { ...item.data, processor } } : item))}/>
              : edge ? <ConnectionInspector key={edge.id} connection={edge.data!.connection} queue={editor?.queue ?? {}}
                relationships={relationshipsOf(edge.source)}
                errors={errors.filter(error => error.startsWith(`Connection ${edge.id}:`) || error.startsWith(`Connection ${edge.id},`))}
                disabled={readOnly} remove={() => {
                  setEdges(current => current.filter(item => item.id !== edge.id))
                  setSelection(undefined)
                }} change={connection => setEdges(current => current.map(item => item.id === edge.id
                  ? { ...item, data: { connection }, label: connection.label || connection.source_relationship } : item))}/>
              : service && editor?.controller_services[service.type] ? <ServiceInspector key={service.id} service={service}
                schema={editor.controller_services[service.type]} services={serviceOptions} disabled={readOnly}
                errors={errors.filter(error => error.startsWith(`Controller service ${service.id}:`)
                  || error.startsWith(`Controller service ${service.id},`))}
                change={next => setMetadata(current => ({ ...current, controller_services: current.controller_services?.map(item =>
                  item.id === next.id ? next : item) }))}
                remove={() => {
                  setMetadata(current => ({ ...current, controller_services: current.controller_services?.filter(item =>
                    item.id !== service.id) }))
                  setSelection(undefined)
                }}/>
                : <aside className="inspector">
                  <div className="inspector-title"><h2>Flow settings</h2></div>
                  <div className="inspector-content">
                    <label className="input-field">Description<textarea rows={4} value={metadata.description ?? ''} disabled={readOnly}
                      onChange={event => setMetadata({ ...metadata, description: event.target.value || null })}/></label>
                    {catalog && nodes.length > 0 && <p className="muted">Select a processor or connection to edit its configuration.</p>}
                  </div>
                </aside>}
          </div>
          {errors.length > 0 && <div className="validation-panel"><h2>Validation issues</h2>
            <ul>{errors.map((error, index) => <li key={index}>{error}</li>)}</ul></div>}
        </div>
      </div>}
      {tab === 'agents' && <AgentInventory showDeployments={id => { setDeploymentFilter(id); setTab('deployments') }}/>}
      {tab === 'deployments' && <DeploymentInventory key={deploymentFilter} initialAgent={deploymentFilter}/>}
    </main>
  </div>
}
