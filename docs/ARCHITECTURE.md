# Architecture and component specification

## Constraints
- 100–1000 agents; Windows x64, Linux x64, Linux ARM64.
- Edge devices are outbound-only.
- Independent advanced flow designer.
- Initial protocol families: MQTT, Modbus TCP, OPC UA, HTTP/REST, files, Kafka, SQL, TCP/UDP.
- Self-hosted and open-source-first.

## Planes
Control plane: React/TypeScript UI, FastAPI API, PostgreSQL, Redis worker queue, S3-compatible
artifact store, Git repository, MiNiFi C2 adapter, compiler and monitoring.

Edge data plane: MiNiFi C++ runtime, local flow/content repositories, outbound C2 client and
protocol-specific processors/extensions.

## Canonical flow model
OEM Flow DSL is the source of truth. A versioned compiler translates approved nodes to the
pinned runtime configuration schema. Compiler outputs are immutable artifacts with SHA-256,
runtime version, OS, architecture, processor catalogue version and DSL version metadata.

## Designer requirements
- Processor palette with search/categories.
- Node configuration panels generated from JSON Schema.
- Typed ports and relationship names.
- Queue/connection settings and back-pressure controls.
- Validation warnings/errors on canvas.
- Parameter contexts and environment-specific values.
- Groups, reusable templates and annotations.
- Draft/published versions, diff and rollback.
- Target-class compatibility preview.

## Processor capability catalogue
Each entry records OEM type, exact runtime build, OS/architecture availability, property schema,
relationships, extension dependencies, licence metadata and integration-test status.
A processor must not be considered deployable just because a similarly named NiFi processor exists.

| Protocol | Initial implementation direction | Qualification |
|---|---|---|
| Files | MiNiFi C++ file processors | Verify exact build |
| HTTP/REST | MiNiFi C++ HTTP processors | Verify TLS/proxy behavior |
| MQTT | MiNiFi C++ MQTT processors | Verify broker/auth/QoS |
| TCP/UDP | MiNiFi C++ socket processors | Verify processor availability |
| Kafka | Runtime processor or extension | Build/integration test |
| SQL | Runtime DB processors and drivers | Driver/licence matrix |
| Modbus TCP | Custom C++ extension or local gateway | Not assumed built-in |
| OPC UA | Custom extension or local gateway | Not assumed built-in |

Start MVP with files, HTTP, MQTT and TCP. Add Kafka/SQL after compatibility tests.
Treat Modbus/OPC UA as dedicated extension work until proven otherwise.

## Outbound-only deployment
Agents initiate HTTPS connections. No inbound edge listener is required. The control plane
returns pending work through the selected C2 protocol. Large artifacts are fetched via HTTPS
using short-lived scoped credentials. Deployments are idempotent and correlated by deployment
ID and artifact digest.

## MiNiFi C2 boundary
Implement a dedicated adapter against the official C2 protocol and a pinned MiNiFi C++ release.
Contract tests must cover heartbeat, UPDATE/TRANSFER, artifact URL handling, ACK success/failure,
retries, duplicate messages, identity, TLS and reconnect. OEM's dev heartbeat endpoint is not C2.

## Deployment state machine
DRAFT -> VALIDATED -> PUBLISHED -> PENDING -> DOWNLOADING -> STAGED -> APPLYING -> SUCCESS.
Failure branches: VALIDATION_FAILED, DOWNLOAD_FAILED, APPLY_FAILED, TIMED_OUT.
Rollback is a new deployment of a previous immutable artifact.

## Scale and availability
Use stateless API/C2 instances behind a reverse proxy. PostgreSQL is source of truth; Redis is
only queue/cache. Use jittered heartbeat intervals and exponential backoff. Batch bulk rollout.
Test 1000 agents, reconnect storms, large artifacts and database failover.

## Non-goals for v1
No arbitrary remote shell execution, no inbound edge access, no universal NiFi processor support,
and no exactly-once guarantee across arbitrary external systems.
