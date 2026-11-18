# Implementation plan

## Local development baseline

The audit found the following issues on the starting branch.

| Finding | Status |
| --- | --- |
| The historical `minio/minio:latest` pull failed. The current Silo image was already an interim replacement tied to MinIO configuration. | Replaced with the maintained Apache-2.0 SeaweedFS 4.54 release and its published multi-platform digest. The old volume is preserved. |
| The agent override pointed to a Java image, mounted the entire configuration directory, lacked a flow, and used the nonexistent Compose host `backend`. | The `agent` profile builds from the official pinned C++ image, retains its packaged defaults, and uses the Compose service name `api`. |
| Python transitive dependencies and npm installations were unpinned. PostgreSQL settings could disagree with the API URL. | Locked both dependency trees. Compose shares PostgreSQL settings with the API, which builds the URL safely. |
| Browser requests crossed origins, and only PostgreSQL had meaningful Compose startup gating. | Vite proxies management calls on the same origin. Compose checks API database readiness, UI, Redis, S3 and the agent process. |
| The C2 stub had no protocol implementation. The compiler, catalog and deployment flow were incomplete. | C2 heartbeat and acknowledgement are implemented. Runtime compilation, capability validation, and deployment execution are planned. |
| The original FastAPI dependency resolved Starlette 0.46.2 with published security advisories. | Updated FastAPI and locked Starlette 1.10.0. |
| The scaffold exposed development ports and relied on default credentials. Management and agent identity were unauthenticated. | Only UI and API ports bind to loopback. Authentication, authorization, TLS and rate limiting remain required for production. |

## Verification

| Check | Result |
| --- | --- |
| Docker Compose configuration | Validated default, `agent`, `smoke`, and trusted build CA configurations. |
| Pinned images and locked dependencies | Resolved and built on Linux amd64 using Docker Engine 29.9.2 and Compose 2.40.3. A BuildKit CA secret supplied the test environment's TLS proxy trust. |
| Backend and frontend | Backend container started and passed PostgreSQL readiness. Frontend `tsc -b` and `vite build` passed in the Docker build. |
| Live integration | **6/6 passed** in a fresh Compose project. Covered real C++ heartbeat (200) and persisted `FULLY_APPLIED` ACK (204), duplicate and conflicting ACKs, C2 validation, API/UI proxy, Redis, and signed S3 object I/O with anonymous access denied. |
| Dependency advisory scans | `npm audit` and `pip-audit` for both Python lockfiles reported zero known vulnerabilities at verification time. |
| Platform coverage | Ran Linux amd64 containers. Verified Linux amd64 and arm64 manifests for the pinned MiNiFi and SeaweedFS images. Windows PowerShell, native Windows agents, and Linux arm64 execution were untested. |

Apache MiNiFi C++ wire behavior was checked against the pinned upstream
[RESTSender and RESTProtocol sources](https://github.com/apache/nifi-minifi-cpp/tree/1a4b84eb8b53eebcf7c92d83f6ae818f440e33ee/libminifi/src/c2/protocols).

## Phase 0 — Runtime spike (2–3 weeks)

Expand the tested runtime/build matrix to Windows x64 and Linux ARM64. Verify processor
availability and offline/reconnect behavior. Prove `GetFile -> InvokeHTTP` with a real agent
and a test receiver before claiming data-plane support.

## Phase 1 — Control plane MVP (3–5 weeks)

Add schema migrations and authenticated enrollment. Extend C2 contract tests to mTLS and
operation delivery. Integrate the artifact store and verify downloaded artifacts by digest.
Use authenticated agent identity and persistent operation IDs to correlate delivery outcomes.

## Phase 2 — Designer and DSL (4–6 weeks)
React Flow palette/forms, JSON Schema processor definitions, DSL validator, compiler for an
approved subset, versioning and immutable artifacts.
Exit: author, validate, compile and inspect a test flow.

## Phase 3 — Fleet deployment (3–4 weeks)
Target selection, staged rollout, download/apply/ACK, retries, timeouts, idempotency, rollback,
fleet UI and audit.
Exit: staged deployment to a mixed 20-agent test fleet.

## Phase 4 — Protocol extensions (4–8+ weeks)
Files/HTTP/MQTT/TCP first; Kafka and SQL after build/driver validation; Modbus and OPC UA custom
extension or gateway evaluation.
Exit: integration tests against representative real devices and brokers.

## Phase 5 — Production hardening (3–4 weeks)
OIDC/RBAC, mTLS/certificate rotation, HA database/API, monitoring, backups, 1000-agent load and
reconnect-storm tests, security review and disaster recovery.

Estimates assume a 3–4 person experienced team; protocol work and processor availability may
change the schedule.
