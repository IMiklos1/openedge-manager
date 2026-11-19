import { useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import type {
  ComponentSchema, ControllerService, Field, FlowConnection, Processor, ProcessorSchema, ServiceSchema, Value, Values,
} from './api'

type ServiceOption = { id: string; name: string; apis: string[] }

function Fields({ fields, values, change, disabled, services = [] }: {
  fields: Record<string, Field>
  values: Values
  change: (values: Values) => void
  disabled: boolean
  services?: ServiceOption[]
}) {
  return <>{Object.entries(fields).map(([key, field]) => {
    const value = values[key] ?? field.default
    const assign = (next: Value) => {
      if (next === '') {
        const copy = { ...values }
        delete copy[key]
        change(copy)
      } else {
        change({ ...values, [key]: next })
      }
    }
    const label = field.label ?? key
    const applies = Object.entries(field.dependencies ?? {}).every(([name, options]) => {
      const current = values[name] ?? fields[name]?.default
      return current !== undefined && current !== '' && (!options.length || options.includes(String(current)))
    })
    const details = [
      field.description, field.sensitive && 'Sensitive values need a dedicated secret integration.',
      field.modifies_classpath && 'Use resources provisioned on the target agent.',
      field.expression_scope && field.expression_scope !== 'NONE' && `Expression Language scope: ${field.expression_scope}`,
      !applies && 'Applies when its dependent properties are configured.',
    ].filter(Boolean).join(' ')
    const options = services.filter(service => field.service && service.apis.includes(field.service))
    const supportsExpression = field.expression_scope && field.expression_scope !== 'NONE' && field.choices?.length
    const inactive = disabled || field.sensitive
    return <label className={field.type === 'boolean' && !supportsExpression ? 'check-field' : 'input-field'} key={key} title={details}>
      <span>{label}{field.required && applies && <small aria-hidden="true"> *</small>}</span>
      {field.sensitive ? <input aria-label={label} disabled placeholder="Sensitive property" /> :
        field.type === 'service' ? <select aria-label={label} disabled={inactive} value={String(value ?? '')}
          onChange={event => assign(event.target.value)}>
          <option value="">Select a controller service</option>
          {value && !options.some(option => option.id === value) && <option value={String(value)}>Unavailable ({value})</option>}
          {options.map(option => <option value={option.id} key={option.id}>{option.name}</option>)}
        </select> : field.type === 'boolean' && !supportsExpression
          ? <input aria-label={label} type="checkbox" checked={String(value).toLowerCase() === 'true'} disabled={inactive}
              onChange={event => assign(event.target.checked)} />
          : field.type === 'choice' && !supportsExpression
            ? <select aria-label={label} disabled={inactive} value={String(value ?? '')} onChange={event => assign(event.target.value)}>
                {field.default === undefined && <option value="">Select a value</option>}
                {value && !field.choices?.includes(String(value)) && <option value={String(value)}>{value}</option>}
                {field.choices?.map(choice => <option value={choice} key={choice}>{field.choice_labels?.[choice] ?? choice}</option>)}
              </select>
            : field.multiline
              ? <textarea aria-label={label} rows={3} value={String(value ?? '')} maxLength={field.max} disabled={inactive}
                  onChange={event => assign(event.target.value)} />
              : <input aria-label={label} type={field.type === 'integer' ? 'number' : 'text'} min={field.min}
                  max={field.type === 'integer' ? field.max : undefined} disabled={inactive}
                  placeholder={field.type === 'size' ? 'e.g. 2 KB' : field.type === 'duration' ? 'e.g. 5 sec' : undefined}
                  value={String(value ?? '')} onChange={event => assign(
                    field.type === 'integer' && event.target.value ? event.target.valueAsNumber : event.target.value,
                  )} />}
      {!!supportsExpression && <small>Values: {field.choices?.join(', ')} or a NiFi expression</small>}
      {!!details && field.type !== 'boolean' && <small className="field-help">{details}</small>}
    </label>
  })}</>
}

function ComponentProperties({ component, schema, change, disabled, services }: {
  component: Processor | ControllerService
  schema: ComponentSchema
  change: (values: { config: Values; attributes?: Record<string, string> }) => void
  disabled: boolean
  services: ServiceOption[]
}) {
  const [attribute, setAttribute] = useState('')
  const [value, setValue] = useState('')
  const attrs = component.attributes ?? {}
  const isGenerator = component.type === 'GenerateFlowFile'
  return <>
    <p className="muted">{schema.description}</p>
    <Fields fields={schema.properties} values={component.config} disabled={disabled} services={services}
      change={config => change({ config, attributes: component.attributes })}/>
    {schema.dynamic_properties && <fieldset className="attributes">
      <legend>{isGenerator ? 'Generated attributes' : 'Dynamic properties'}</legend>
      {!isGenerator && schema.dynamic?.map((item, index) => <p className="muted" key={index}>{item.description}</p>)}
      {Object.entries(attrs).map(([key, current]) => <div className="attribute-row" key={key}>
        <label className="input-field">{key}<textarea aria-label={key} value={current} rows={2} disabled={disabled}
          onChange={event => change({ config: component.config, attributes: { ...attrs, [key]: event.target.value } })}/></label>
        <button type="button" className="icon-button" aria-label={`Remove ${key}`} disabled={disabled} onClick={() => {
          const copy = { ...attrs }
          delete copy[key]
          change({ config: component.config, attributes: copy })
        }}><Trash2 size={14}/></button>
      </div>)}
      <label className="input-field">{isGenerator ? 'Attribute name' : 'Dynamic property name'}<input value={attribute}
        disabled={disabled} onChange={event => setAttribute(event.target.value)}/></label>
      <label className="input-field">{isGenerator ? 'Attribute value' : 'Dynamic property value'}<textarea value={value} rows={2}
        disabled={disabled} onChange={event => setValue(event.target.value)}/></label>
      <button type="button" disabled={disabled || !attribute.trim() || (isGenerator && !value.trim())
        || Object.prototype.hasOwnProperty.call(attrs, attribute.trim()) || Object.prototype.hasOwnProperty.call(schema.properties, attribute.trim())}
        onClick={() => {
          change({ config: component.config, attributes: { ...attrs, [attribute.trim()]: value } })
          setAttribute('')
          setValue('')
        }}><Plus size={14}/> {isGenerator ? 'Add attribute' : 'Add dynamic property'}</button>
    </fieldset>}
  </>
}

function Errors({ errors }: { errors: string[] }) {
  return errors.length > 0 && <ul className="validation-errors">{errors.map((error, index) => <li key={index}>{error}</li>)}</ul>
}

export function ProcessorInspector({ node, schema, change, disabled, errors, services, relationships, connected }: {
  node: Processor
  schema?: ProcessorSchema
  change: (node: Processor) => void
  disabled: boolean
  errors: string[]
  services: ServiceOption[]
  relationships: string[]
  connected: string[]
}) {
  const [section, setSection] = useState('Properties')
  const terminated = node.auto_terminate ?? relationships.filter(relationship => !connected.includes(relationship))
  return <section aria-label="Processor settings" className="inspector">
    <div className="inspector-title"><span className="section-label">Processor</span><h2>{node.label || node.type}</h2>
      <span className="muted">{node.type}</span></div>
    <div className="inspector-tabs" aria-label="Processor settings sections">
      {['Properties', 'Scheduling', 'Relationships', 'General'].map(tab => <button type="button" key={tab}
        className={section === tab ? 'chosen' : ''} aria-pressed={section === tab}
        onClick={() => setSection(tab)}>{tab}</button>)}
    </div>
    <div className="inspector-content">
      {section === 'General' ? <>
        <label className="input-field">Processor name<input value={node.label ?? ''} placeholder={node.type} disabled={disabled}
          onChange={event => change({ ...node, label: event.target.value || null })}/></label>
        <label className="input-field">Comments<textarea value={node.description ?? ''} disabled={disabled}
          onChange={event => change({ ...node, description: event.target.value || null })}/></label>
        {schema && <p className="muted">{schema.bundle.artifact} {schema.bundle.version}</p>}
      </> : !schema ? <p className="muted">This processor is outside the pinned Java image.</p>
        : section === 'Scheduling' ? <>
          <div className="muted">Timer driven</div>
          <Fields fields={Object.fromEntries(Object.entries(schema.scheduling).filter(([key]) => key !== 'retry_success'))}
            values={node.scheduling ?? {}} disabled={disabled} change={scheduling => change({ ...node, scheduling })}/>
        </> : section === 'Relationships' ? <>
          <label className="check-field"><span>Terminate unconnected relationships automatically</span>
            <input type="checkbox" checked={node.auto_terminate == null} disabled={disabled}
              onChange={event => change({ ...node, auto_terminate: event.target.checked ? null : terminated, auto_terminate_success: null })}/>
          </label>
          {relationships.map(relationship => {
            const legacyRetry = node.scheduling?.retry_success === true || node.scheduling?.retry_success === 'true'
            const retry = node.retry_relationships?.includes(relationship) || (legacyRetry && relationship === 'success')
            return <fieldset className="attributes" key={relationship}>
              <legend>{relationship}</legend>
              {schema.relationships[relationship]?.description && <small>{schema.relationships[relationship].description}</small>}
              <label className="check-field"><span>{connected.includes(relationship) ? 'Connected' : 'Terminate'}</span>
                <input type="checkbox" checked={terminated.includes(relationship)}
                  disabled={disabled || node.auto_terminate == null || connected.includes(relationship)}
                  onChange={event => change({ ...node, auto_terminate: event.target.checked
                    ? [...terminated, relationship] : terminated.filter(item => item !== relationship) })}/></label>
              <label className="check-field"><span>Retry</span><input type="checkbox" checked={retry} disabled={disabled}
                onChange={event => change({ ...node,
                  scheduling: { ...node.scheduling, retry_success: false },
                  retry_relationships: event.target.checked ? [...new Set([...(node.retry_relationships ?? []),
                    ...(legacyRetry ? ['success'] : []), relationship])]
                    : (node.retry_relationships ?? []).filter(item => item !== relationship),
                })}/></label>
            </fieldset>
          })}
        </> : <ComponentProperties component={node} schema={schema} disabled={disabled} services={services}
          change={values => change({ ...node, ...values })}/>}
      <Errors errors={errors}/>
    </div>
  </section>
}

export function ServiceInspector({ service, schema, services, change, remove, disabled, errors }: {
  service: ControllerService
  schema: ServiceSchema
  services: ServiceOption[]
  change: (next: ControllerService) => void
  remove: () => void
  disabled: boolean
  errors: string[]
}) {
  return <section className="inspector" aria-label="Controller service settings">
    <div className="inspector-title"><h2>{service.type}</h2></div>
    <div className="inspector-content">
      <label className="input-field">Service name<input value={service.label ?? ''} placeholder={service.type} disabled={disabled}
        onChange={event => change({ ...service, label: event.target.value || null })}/></label>
      <label className="input-field">Comments<textarea value={service.description ?? ''} disabled={disabled}
        onChange={event => change({ ...service, description: event.target.value || null })}/></label>
      <label className="input-field">Initial state<select value={service.state ?? 'ENABLED'} disabled={disabled}
        onChange={event => change({ ...service, state: event.target.value === 'DISABLED' ? 'DISABLED' : 'ENABLED' })}>
        <option>ENABLED</option><option>DISABLED</option>
      </select></label>
      <ComponentProperties component={service} schema={schema} services={services.filter(item => item.id !== service.id)}
        disabled={disabled} change={values => change({ ...service, ...values })}/>
      <button onClick={remove} disabled={disabled}>Remove service</button>
      <Errors errors={errors}/>
    </div>
  </section>
}

export function ConnectionInspector({ connection, queue, relationships, change, remove, disabled, errors }: {
  connection: FlowConnection
  queue: Record<string, Field>
  relationships: string[]
  change: (connection: FlowConnection) => void
  remove: () => void
  disabled: boolean
  errors: string[]
}) {
  const options = [...new Set([connection.source_relationship, ...relationships])]
  return <section className="inspector" aria-label="Connection settings">
    <div className="inspector-title"><span className="section-label">Connection</span><h2>{connection.label || connection.source_relationship}</h2></div>
    <div className="inspector-content">
      <label className="input-field">Connection name<input value={connection.label ?? ''} disabled={disabled}
        onChange={event => change({ ...connection, label: event.target.value || null })}/></label>
      <label className="input-field">Relationship<select aria-label="Relationship" value={connection.source_relationship} disabled={disabled}
        onChange={event => change({ ...connection, source_relationship: event.target.value })}>
        {options.map(option => <option key={option}>{option}</option>)}
      </select></label>
      <Fields fields={queue} values={connection.queue ?? {}} disabled={disabled} change={value => change({ ...connection, queue: value })}/>
      <button onClick={remove} disabled={disabled}>Remove connection</button>
      <Errors errors={errors}/>
    </div>
  </section>
}
