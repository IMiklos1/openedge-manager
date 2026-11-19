import { useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import type { Field, FlowConnection, Processor, ProcessorSchema, Value, Values } from './api'

function Fields({ fields, values, change, disabled }: {
  fields: Record<string, Field>
  values: Values
  change: (values: Values) => void
  disabled: boolean
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
    return <label className={field.type === 'boolean' ? 'check-field' : 'input-field'} key={key}>
      <span>{label}</span>
      {field.type === 'boolean'
        ? <input aria-label={label} type="checkbox" checked={value === true || value === 'true'} disabled={disabled}
            onChange={event => assign(event.target.checked)} />
        : field.type === 'choice'
          ? <select aria-label={label} disabled={disabled} value={String(value ?? '')} onChange={event => assign(event.target.value)}>
              {field.choices?.map(choice => <option key={choice}>{choice}</option>)}
            </select>
          : field.multiline
            ? <textarea aria-label={label} rows={3} value={String(value ?? '')} maxLength={field.max} disabled={disabled}
                onChange={event => assign(event.target.value)} />
            : <input aria-label={label} type={field.type === 'integer' ? 'number' : 'text'} min={field.min}
                max={field.type === 'integer' ? field.max : undefined} disabled={disabled}
                placeholder={field.type === 'size' ? 'e.g. 2 KB' : field.type === 'duration' ? 'e.g. 5 sec' : undefined}
                value={String(value ?? '')} onChange={event => assign(
                  field.type === 'integer' && event.target.value ? event.target.valueAsNumber : event.target.value,
                )} />}
    </label>
  })}</>
}

export function ProcessorInspector({ node, schema, change, disabled, errors }: {
  node: Processor
  schema?: ProcessorSchema
  change: (node: Processor) => void
  disabled: boolean
  errors: string[]
}) {
  const [section, setSection] = useState('Properties')
  const [attribute, setAttribute] = useState('')
  const [value, setValue] = useState('')
  const attrs = node.attributes ?? {}
  return <section aria-label="Processor settings" className="inspector">
    <div className="inspector-title"><span className="section-label">Processor</span><h2>{node.label || node.type}</h2>
      <span className="muted">{node.type}</span></div>
    <div className="inspector-tabs" aria-label="Processor settings sections">
      {['Properties', 'Scheduling', 'General'].map(tab => <button type="button" key={tab}
        className={section === tab ? 'chosen' : ''} aria-pressed={section === tab}
        onClick={() => setSection(tab)}>{tab}</button>)}
    </div>
    <div className="inspector-content">
      {section === 'General' ? <>
        <label className="input-field">Processor name<input value={node.label ?? ''} placeholder={node.type} disabled={disabled}
          onChange={event => change({ ...node, label: event.target.value || null })}/></label>
        <label className="input-field">Comments<textarea value={node.description ?? ''} disabled={disabled}
          onChange={event => change({ ...node, description: event.target.value || null })}/></label>
        {schema && <label className="input-field">Success relationship<select value={String(node.auto_terminate_success ?? 'auto')}
          disabled={disabled} onChange={event => change({
            ...node, auto_terminate_success: event.target.value === 'auto' ? null : event.target.value === 'true',
          })}>
          <option value="auto">Use connections</option><option value="true">Terminate</option><option value="false">Route to a connection</option>
        </select></label>}
      </> : !schema ? <p className="muted">Configuration is unavailable for this processor in the current Java profile.</p>
        : section === 'Scheduling' ? <>
          <div className="muted">Timer driven</div>
          <Fields fields={schema.scheduling} values={node.scheduling ?? {}} disabled={disabled}
            change={scheduling => change({ ...node, scheduling })}/>
        </> : <>
          <p className="muted">{schema.description}</p>
          <Fields fields={schema.properties} values={node.config} disabled={disabled}
            change={config => change({ ...node, config })}/>
          {schema.dynamic_properties && <fieldset className="attributes">
            <legend>Generated attributes</legend>
            {Object.entries(attrs).map(([key, current]) => <div className="attribute-row" key={key}>
              <label className="input-field">{key}<input value={current} disabled={disabled}
                onChange={event => change({ ...node, attributes: { ...attrs, [key]: event.target.value } })}/></label>
              <button type="button" className="icon-button" aria-label={`Remove ${key}`} disabled={disabled} onClick={() => {
                const copy = { ...attrs }
                delete copy[key]
                change({ ...node, attributes: copy })
              }}><Trash2 size={14}/></button>
            </div>)}
            <label className="input-field">Attribute name<input value={attribute} disabled={disabled}
              onChange={event => setAttribute(event.target.value)}/></label>
            <label className="input-field">Attribute value<input value={value} disabled={disabled}
              onChange={event => setValue(event.target.value)}/></label>
            <button type="button" disabled={disabled || !attribute.trim() || !value.trim() || Object.prototype.hasOwnProperty.call(attrs, attribute.trim())}
              onClick={() => {
                change({ ...node, attributes: { ...attrs, [attribute.trim()]: value } })
                setAttribute('')
                setValue('')
              }}><Plus size={14}/> Add attribute</button>
          </fieldset>}
        </>}
      {errors.length > 0 && <ul className="validation-errors">{errors.map((error, index) => <li key={index}>{error}</li>)}</ul>}
    </div>
  </section>
}

export function ConnectionInspector({ connection, queue, change, disabled, errors }: {
  connection: FlowConnection
  queue: Record<string, Field>
  change: (connection: FlowConnection) => void
  disabled: boolean
  errors: string[]
}) {
  return <section className="inspector" aria-label="Connection settings">
    <div className="inspector-title"><span className="section-label">Connection</span><h2>{connection.label || connection.source_relationship}</h2></div>
    <div className="inspector-content">
      <label className="input-field">Connection name<input value={connection.label ?? ''} disabled={disabled}
        onChange={event => change({ ...connection, label: event.target.value || null })}/></label>
      <label className="input-field">Relationship<input value={connection.source_relationship} disabled={disabled}
        onChange={event => change({ ...connection, source_relationship: event.target.value })}/></label>
      <Fields fields={queue} values={connection.queue ?? {}} disabled={disabled} change={value => change({ ...connection, queue: value })}/>
      {errors.length > 0 && <ul className="validation-errors">{errors.map((error, index) => <li key={index}>{error}</li>)}</ul>}
    </div>
  </section>
}
