# API specification (starter)

Management routes use `/api/v1` except for readiness at `/health`.

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` (root) | API and database readiness |
| GET | `/agents` | List agents |
| GET | `/catalog` | Processor catalogue |
| POST | `/agents/{id}/heartbeat` | OEM development heartbeat only |
| POST | `/flows` | Create draft flow |
| GET | `/flows` | List flows |
| GET | `/flows/{id}` | Read flow |
| POST | `/flows/{id}/publish` | Compile and publish an immutable Java artifact |
| POST | `/deployments` | Queue a published flow for one enabled agent |
| GET | `/deployments/{id}` | Read deployment and acknowledgement status |

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
