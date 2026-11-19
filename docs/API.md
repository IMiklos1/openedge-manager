# API specification (starter)

Management routes use `/api/v1` except for readiness at `/health`.

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` (root) | API and database readiness |
| GET | `/agents` | List agents by class or ID/hostname search with heartbeat freshness |
| GET | `/agent-classes` | List observed classes and recent check-in counts |
| GET | `/catalog` | Processor catalogue and supported configuration fields |
| GET | `/flow-editor` | Supported queue settings and runtime version |
| POST | `/agents/{id}/heartbeat` | OEM development heartbeat only |
| POST | `/flows` | Create draft flow |
| GET | `/flows` | List flows |
| GET | `/flows/{id}` | Read latest saved flow |
| PUT | `/flows/{id}` | Save an updated graph as a revision using `expected_version` |
| GET | `/flows/{id}/versions` | List saved revisions and published digests |
| GET | `/flows/{id}/versions/{version}` | Read a specific revision |
| POST | `/flows/{id}/publish` | Compile and publish an immutable Java artifact |
| POST | `/deployments` | Queue a published flow for one enabled agent |
| GET | `/deployments/{id}` | Read deployment and acknowledgement status |
| GET | `/deployments` | List history filtered by agent, flow, or state |

Production requirements: OIDC login, RBAC, per-agent mTLS identity, idempotency keys,
pagination, audit events, rate limits, request-size limits and versioned OpenAPI.

Suggested next endpoints: flow validate/version/diff, deployment cancel/targets, agent
certificate rotation and diagnostics.

## MiNiFi Java 2.12.0 C2

These development routes are at the API root. Both accept uncompressed JSON with
`Content-Type: application/json` and a 4 MiB body limit. They return 415 for an unsupported
media type or encoding, 413 for an oversized body, and 422 for an invalid message.

| Method | Path | Behavior |
| --- | --- | --- |
| POST | `/c2-protocol/heartbeat` | Requires `agentInfo.identifier`. Accepts agent class, manifest version and device metadata. Upserts inventory and returns HTTP 200 with a `requestedOperations` array. |
| POST | `/c2-protocol/acknowledge` | Requires `operationId` and `operationState.state`. If supplied, `agentInfo.identifier` must match the probe target. Records the first outcome and returns HTTP 204 with an empty body, including for an identical replay. An unknown operation or agent mismatch returns 404. A conflicting state returns 409. |

A C2 configuration update uses `operation: "UPDATE"` and `operand: "CONFIGURATION"`.
Its `identifier` is the deployment ID. The `args` object carries the artifact SHA-256
as `flowId` and the relative download path as `relativeFlowUrl`. The agent initiates
`GET /c2-protocol/configuration/{operation_id}` to download the dispatched JSON artifact.
The response has an ETag containing its SHA-256 and `Cache-Control: no-store`.

The array is normally empty. With `MINIFI_PROBE_AGENT_ID` set, the matching test agent can
receive one persistent operation with `identifier`, `operation: "DESCRIBE"`, and
`operand: "MANIFEST"`. Supported ACK states from the pinned client are `FULLY_APPLIED`, `PARTIALLY_APPLIED`, `OPERATION_NOT_UNDERSTOOD`,
`NO_OPERATION`, and `NOT_APPLIED`. The Java client supplies agent information on a successful manifest ACK. Some failure ACKs omit it and are correlated by operation ID. Additional ACK metadata is discarded.


## Test deployment lifecycle

`POST /api/v1/flows/{id}/publish` returns the immutable artifact's flow version,
`runtime_version`, and `sha256`. Repeating publication returns the existing artifact.
Unsupported graphs and properties return 422 and leave the draft intact.

`POST /api/v1/deployments` with `flow_id` and `agent_id` queues a published artifact for
the local opt-in agent. A wrong target returns 403. An incompatible agent, unpublished
artifact, or overlapping active deployment returns 409. A class-only request keeps the
legacy metadata-only behavior.

A deployment moves from `PENDING` to `DISPATCHED` when offered in a heartbeat response.
A successful agent ACK (`FULLY_APPLIED` or `NO_OPERATION`) sets `ACKNOWLEDGED`.
`APPLIED` requires a later heartbeat with the matching `flowInfo.flowId` and
`runStatus: "RUNNING"`. A negative ACK sets `FAILED`. Replaying the same ACK retains the
recorded timestamp. The deployment status includes `ack_state`, `acknowledged_at`, and
`applied_at`.


## Versioned workspace

The canonical graph preserves processor `config`, `attributes`, `scheduling`, `description`,
`position`, and relationship termination settings. Connections retain names, relationships
and `queue` settings. The catalog exposes the typed contract for fields available on the
pinned Java profile. The API preserves invalid drafts and reports validation errors against
node/connection IDs. Publication compiles only valid graphs. With `?version=` specified,
publication returns 409 if the caller's draft is behind the latest saved revision.

An explicit `version` in a deployment request selects an already published artifact.
Omitting it requires the latest saved revision to be published. Published artifacts have separate
immutable digest records, so subsequent draft changes preserve existing deployments.

List endpoints accept `offset` and `limit`. Agent health is derived from last-seen time
with a 30-second window. `RECENT` means a heartbeat was received within that window.
Class counts are based on reported agent classes. These data complement C2 deployment
status and leave the legacy inventory `status` field intact.
