# Architecture and component specification

## Constraints
- 100–1000 agents; Windows x64, Linux x64, Linux ARM64.
- Edge devices are outbound-only.
- Independent advanced flow designer.
- Initial protocol families: MQTT, Modbus TCP, OPC UA, HTTP/REST, files, Kafka, SQL, TCP/UDP.
- Self-hosted and open-source-first.

## Planes

The local control plane runs React/TypeScript with a Vite proxy, FastAPI, and PostgreSQL.
The browser uses same-origin requests for the management API and its documentation. The API's
readiness check runs a database query. Redis and the S3-compatible SeaweedFS service are
available inside the Compose network for future job and artifact integrations.

PostgreSQL, Redis AOF, and SeaweedFS persist in separate named volumes. SeaweedFS initializes
the local S3 bucket in `s3data`. The previous MinIO/Silo volume has its own format and requires
an S3-level object migration if it contains data.

The edge data plane uses the official Apache MiNiFi Java 2.12.0 container with its packaged
empty flow and C2 environment settings in `compose.minifi.yaml`. Its bootstrap status
listener binds to container loopback. The agent publishes no ports. Base and infrastructure
image references include multi-architecture manifest digests.

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
| Files | MiNiFi Java file processors | Verify exact build |
| HTTP/REST | MiNiFi Java HTTP processors | Verify TLS/proxy behavior |
| MQTT | MiNiFi Java MQTT processors | Verify broker/auth/QoS |
| TCP/UDP | MiNiFi Java socket processors | Verify processor availability |
| Kafka | Runtime processor or extension | Build/integration test |
| SQL | Runtime DB processors and drivers | Driver/licence matrix |
| Modbus TCP | Custom Java extension or local gateway | Not assumed built-in |
| OPC UA | Custom extension or local gateway | Not assumed built-in |

Start MVP with files, HTTP, MQTT and TCP. Add Kafka/SQL after compatibility tests.
Treat Modbus/OPC UA as dedicated extension work until proven otherwise.

## Outbound-only deployment

In local Compose, the agent sends HTTP requests to the API service over the project network.
Production agents will initiate HTTPS connections, receive pending work in C2 responses, and
fetch artifacts over HTTPS using short-lived credentials. Deployment delivery, artifact digest
verification, and per-deployment status are planned.

## MiNiFi C2 boundary

The adapter handles uncompressed JSON from the MiNiFi Java 2.12.0 HTTP C2 client.
`POST /c2-protocol/heartbeat` upserts agent identity and reported metadata in PostgreSQL,
then returns a `requestedOperations` array. The Compose agent includes its runtime manifest
in each heartbeat. Heartbeats that omit it preserve the recorded version.

To verify the return path, set `MINIFI_PROBE_AGENT_ID` to the test agent identifier. The API
offers a read-only `DESCRIBE MANIFEST` operation with a persistent ID, then records the state
from the agent-initiated `POST /c2-protocol/acknowledge`. An identical ACK can be replayed.
The API stops offering the operation after any reported terminal state. It retains the state
and timestamp and discards the extra ACK payload. The legacy OEM development heartbeat remains a
separate management endpoint.

The smoke suite verifies real check-ins, reported metadata, and persistent ACK correlation.
Production enrollment, TLS, UPDATE/TRANSFER, artifact URLs, reconnect behavior, deployment
outcomes and scale testing are future work. See the [API contract](API.md).

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
