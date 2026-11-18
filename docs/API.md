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
| POST | `/flows/{id}/publish` | Validate/publish metadata |
| POST | `/deployments` | Create deployment request |

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

The array is normally empty. With `MINIFI_PROBE_AGENT_ID` set, the matching test agent can
receive one persistent operation with `identifier`, `operation: "DESCRIBE"`, and
`operand: "MANIFEST"`. Supported ACK states from the pinned client are `FULLY_APPLIED`, `PARTIALLY_APPLIED`, `OPERATION_NOT_UNDERSTOOD`,
`NO_OPERATION`, and `NOT_APPLIED`. The Java client supplies agent information on a successful manifest ACK. Some failure ACKs omit it and are correlated by operation ID. Deployment state
and additional ACK metadata are outside this contract.
