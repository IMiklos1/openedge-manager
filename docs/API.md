# API specification (starter)

Base path: `/api/v1`

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Health |
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
