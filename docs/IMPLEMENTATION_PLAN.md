# Implementation plan

## Local development baseline

The audit found the following issues on the starting branch.

| Finding | Status |
| --- | --- |
| The historical `minio/minio:latest` pull failed. The current Silo image was already an interim replacement tied to MinIO configuration. | Replaced with the maintained Apache-2.0 SeaweedFS 4.54 release and its published multi-platform digest. The old volume is preserved. |
| The Java agent configuration used unrecognized settings, mounted the entire configuration directory, and targeted a nonexistent service named `backend`. | The `agent` profile uses the official digest-pinned MiNiFi Java 2.12.0 image in `compose.minifi.yaml`, with its packaged flow and the `api` service name. |
| Python transitive dependencies and npm installations were unpinned. PostgreSQL settings could disagree with the API URL. | Locked both dependency trees. Compose shares PostgreSQL settings with the API, which builds the URL safely. |
| Browser requests crossed origins, and only PostgreSQL had meaningful Compose startup gating. | Vite proxies management calls on the same origin. Compose checks API database readiness, UI, Redis, S3, and the agent through its Java bootstrap status command. |
| The C2 stub had no protocol implementation. The compiler, catalog and deployment flow were incomplete. | C2 heartbeat and acknowledgement are implemented. Runtime compilation, capability validation, and deployment execution are planned. |
| The original FastAPI dependency resolved Starlette 0.46.2 with published security advisories. | Updated FastAPI and locked Starlette 1.10.0. |
| The scaffold exposed development ports and relied on default credentials. Management and agent identity were unauthenticated. | Only UI and API ports bind to loopback. Authentication, authorization, TLS and rate limiting remain required for production. |

## Verification

| Check | Evidence |
| --- | --- |
| Merged baseline, `c61fc28` | The [main-branch CI run](https://github.com/IMiklos1/openedge-manager/actions/runs/44392719547) passed. The merged Compose suite also passed 6/6 locally. |
| Compose on Linux amd64 | Default, `agent`, `smoke`, explicit agent override, and trusted build CA configurations validated. The backend and frontend built, and all six normal `agent` stack services became healthy. Local execution used Docker Engine 29.9.2 and Compose 2.40.3. The build used a trusted CA secret for this environment's TLS proxy. |
| Exact runtime artifacts | Pulled the official Java 2.12.0 and C++ 1.1.0 images. Both image indices advertise Linux amd64 and arm64. The real C2 heartbeat reported `minifi-java` and version `2.12.0`. See [ADR-007](DECISIONS.md#adr-007--retain-minifi-java-for-the-verified-integration) for platform coverage and the footprint comparison. |
| Real Java heartbeat and ACK | **8/8** tests passed in the updated smoke profile. The fixture forwarded real Java requests to the API. Tests matched agent ID, class, runtime version, hostname, OS, and architecture to PostgreSQL and management API values. A later heartbeat advanced `last_seen`. |
| Command correlation | A real `DESCRIBE MANIFEST` response contained operation `4372520b-e23b-4d46-a5a8-69fb6f89dd40`. The agent returned the same ID and `FULLY_APPLIED`, which PostgreSQL stored. The following heartbeat returned an empty operation list. Additional checks covered identical replay, a conflicting outcome, a mismatched reported agent, and an unknown operation. |
| Service integration | UI and API proxy, Redis, signed SeaweedFS object I/O, and anonymous S3 denial passed. |

Run the suite using the exact [PowerShell or Bash commands in the README](../README.md#run-the-automated-smoke-tests).

**Verified scope.** Linux amd64 Compose, the isolated plaintext Java C2 registration and
read-only command round trip, persistence of reported inventory and ACK, and supporting
service readiness.

**Unverified scope.** Windows PowerShell execution and native Windows agents, Linux ARM64
execution, runtime status expiry when an agent stops, authenticated device identity and mTLS,
device reconnect/retry and failover, flow deployment and rollback, and processor execution.
The Linux image manifests and release artifacts establish availability. The C++ run was an
idle footprint comparison. C++ C2 compatibility with OEM remains unverified.

## Verified flow creation slice

The local Flow Designer can load the test graph, save a draft, publish an immutable
MiNiFi Java 2.12.0 artifact, and deploy it to one explicitly enabled agent. The backend
uses Alembic to adopt an existing schema and add artifact and deployment state. The
test compiler supports GenerateFlowFile and LogAttribute with fixed properties.

The updated Compose suite passed 11 tests on Linux amd64. The workflow test called the
management API through the UI proxy, observed the real agent fetch bytes with the published
SHA-256, matched its `FULLY_APPLIED` ACK to the deployment, and observed LogAttribute
receive a FlowFile in a subsequent heartbeat. It also covered an unsupported draft and
the disabled target. The migration test preserved legacy SQLite rows. The Compose stack
applied both revisions on a fresh PostgreSQL database.

Use the [PowerShell walkthrough and test commands](../README.md#create-and-deploy-the-test-flow)
to reproduce the flow. Native Windows and ARM64 execution, arbitrary processor properties,
deployment expiry, authenticated enrollment, and fleet rollback are unverified.

## Edge management workspace

The workspace covers local flow creation, typed processor and connection editing, draft
revisions, published artifact selection, agent inventory, observed class activity, and
deployment history. Revision 0003 preserves the current saved graph during migration
and adds storage for subsequent versions and indexes for deployment queries.

The configurable Java profile includes GenerateFlowFile and LogAttribute, literal
dynamic attributes on GenerateFlowFile, timer-driven scheduling, and bounded queue
settings. The default Compose integration has one explicitly enabled development
target. Published revisions can be deployed again to that target.

| Status | Evidence |
| --- | --- |
| Verified on Linux amd64 | All 13 Compose smoke tests passed. A real MiNiFi Java 2.12.0 agent downloaded and applied two different revisions, then reapplied the first. The tests checked the downloaded SHA-256, the correlated C2 acknowledgement, and the running configuration reported by the agent. |
| Verified in Chromium | A flow built in the browser retained processor, scheduling and queue settings after reopening from the server. Both revisions reached `APPLIED` on the local agent. The browser opened the earlier revision in read-only mode and filtered deployment history. |
| Unverified | Native Windows and Linux ARM64 agent execution, PowerShell execution, health after agent loss, and the wider processor and scheduling matrix. |

The [README](../README.md#run-the-automated-smoke-tests) contains Compose and browser test commands.

Broader CEM workflows including authenticated enrollment, multi-agent staged rollout,
role-based access, class administration, remote diagnostics, lifecycle control, fleet
events, controller services, and cross-platform runtime qualification are planned.
Product references document the target lifecycle. The pinned Apache Java source defines
the supported runtime contract.

[Cloudera Edge Management](https://www.cloudera.com/products/data-in-motion/edge-management.html) ·
[Cloudera Agent Manager](https://docs.cloudera.com/cem/latest/using-cem/topics/cem-managing-agents.html) ·
[Apache MiNiFi System Admin Guide](https://github.com/apache/nifi/blob/main/minifi/minifi-docs/src/main/markdown/System_Admin_Guide.md#config-file)

## Phase 0 — Runtime spike (2–3 weeks)

Expand the tested runtime/build matrix to Windows x64 and Linux ARM64. Verify processor
availability and offline/reconnect behavior. Prove `GetFile -> InvokeHTTP` with a real agent
and a test receiver before claiming data-plane support.

## Phase 1 — Control plane MVP (3–5 weeks)

Build on the versioned schema and add authenticated enrollment. Extend C2 contract tests to mTLS and
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
