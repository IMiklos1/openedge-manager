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

The edge data plane uses the official Apache MiNiFi Java 2.12.0 container with C2 settings
in `compose.minifi.yaml`. It starts with the packaged empty flow and can reload a published
test flow through C2. Its bootstrap status
listener binds to container loopback. The agent publishes no ports. Base and infrastructure
image references include multi-architecture manifest digests.

## Canonical flow model
OEM Flow DSL is the source of truth. A versioned compiler translates approved nodes to the
pinned runtime configuration schema. Compiler outputs are immutable artifacts with SHA-256,
runtime version and flow version metadata. The compiler uses the stock image's processor
and controller service manifests. It maps properties, service references, relationships,
position, scheduling and queue settings into the
Java 2.12.0 raw-flow JSON model. PostgreSQL stores an immutable graph revision on each save
and a separate immutable artifact on publication. The current flow row uses compare-and-swap
versioning to prevent an editor from overwriting another editor's changes.

Each revision selects Java or C++. Existing definitions without a runtime select Java.
Migration `0004` labels existing artifacts as Java and persists the family alongside
the release version for new artifacts. The C++ compiler emits the native 1.1.0 JSON
flow schema accepted by AdaptiveConfiguration. Stable component IDs and queue settings
use the same canonical model.

## Flow Manager

The workspace loads existing graphs and immutable revisions, edits processors and queues
using the server's schema, and surfaces compile errors with node or connection context.
The fleet views use the persisted agent and deployment APIs for last-seen freshness,
reported classes, deployment attempts, and ACK state. Operators can choose an older
published artifact and any compatible enabled agent explicitly. The editor stores
controller services alongside the graph. Fleet rollout policy and parameter contexts
remain future work.

The target picker shows the inventory and the reason when a device is ineligible.
Compose supplies the built-in test targets if the operator has not configured an explicit
allowlist. The UI publishes the current saved revision before queueing when the operator
chooses **Publish and deploy**. The same publication and deployment endpoints are used
for both that action and the separate publish-then-deploy workflow.
Changing **Flow runtime** loads a separate catalog and preserves any existing draft
settings. Unsupported components or settings must be resolved before publication.

## Processor capability catalogue
The generated catalog takes component classes, bundle coordinates, properties, input rules
and relationships from the stock image's NAR manifests. OEM verifies declared components
against the exact runtime heartbeat before queueing or dispatching a deployment. The
catalog lists 117 processors and 47 controller services. Device-side validators still
govern valid values and external resources. [Catalog provenance and coverage](PROCESSOR_CATALOG.md)
The C++ profile exposes the tested GenerateFlowFile, UpdateAttribute and LogAttribute
processors with C++ property names. C++ controller services and relationship retry
configuration are outside this profile.

## Outbound-only deployment

The NiFi overlay adds HTTP Site-to-Site to the same Compose project. The API reads
ports from NiFi's Site-to-Site catalog. Flow revisions store the selected UUID,
and each runtime's configuration connects the graph to a local sending port
with the NiFi target UUID. The edge agent makes the data connection. The receiving
flow verifies data delivery independently of C2 deployment state.

In local Compose, the agent sends HTTP requests to the API service over the project network.
Production agents will initiate HTTPS connections, receive pending work in C2 responses, and
fetch artifacts over HTTPS using short-lived credentials. In the local slice, the agent
downloads the JSON over its existing C2 connection after receiving an update operation.
The backend tracks the artifact digest and per-deployment status.

## MiNiFi C2 boundary

The adapter handles uncompressed JSON from MiNiFi Java 2.12.0 and MiNiFi C++ 1.1.0.
`POST /c2-protocol/heartbeat` upserts agent identity and reported metadata in PostgreSQL,
then returns a `requestedOperations` array. The Compose agents send their manifests in
heartbeats. The API detects Java by `minifi-java` and native C++ by `cpp`, and persists
component identities from the manifest. Heartbeats without the manifest preserve the
recorded runtime, version and component list.

To verify the return path, set `MINIFI_PROBE_AGENT_ID` to the test agent identifier. The API
offers a read-only `DESCRIBE MANIFEST` operation with a persistent ID, then records the state
from the agent-initiated `POST /c2-protocol/acknowledge`. An identical ACK can be replayed.
The API stops offering the operation after any reported terminal state. It retains the state
and timestamp and discards the extra ACK payload. The legacy OEM development heartbeat remains a
separate management endpoint.

The smoke profile runs the same pinned Java image with a separate agent ID. Its test-only
observer forwards C2 traffic and retains selected fields in memory. Tests compare the actual
heartbeat to the API and PostgreSQL, then match the returned command identifier with the live
ACK and stored probe. The adapter also checks the reported agent ID when the ACK includes it.
The Java `UPDATE CONFIGURATION` operation uses the raw JSON pattern from the Apache
[System Admin Guide](https://github.com/apache/nifi/blob/main/minifi/minifi-docs/src/main/markdown/System_Admin_Guide.md#config-file)
and the pinned [Java operation handler](https://github.com/apache/nifi/blob/19f4df8e048e91d87d3e4967c69b1298f9dbe450/c2/c2-client-bundle/c2-client-service/src/main/java/org/apache/nifi/c2/client/service/operation/UpdateConfigurationOperationHandler.java).
The C++ adapter uses `location`, `persist` and `flowId`. Its flow base URL resolves the
download path. Both formats are served over the same C2 download endpoint.
[Pinned C++ configuration handler](https://github.com/apache/nifi-minifi-cpp/blob/1a4b84eb8b53eebcf7c92d83f6ae818f440e33ee/libminifi/src/c2/C2Agent.cpp)
The read-only manifest probe remains available. Production enrollment, TLS, transfer,
rollback, timeout recovery, and scale testing are future work. See the [API contract](API.md) and
[runtime decision](DECISIONS.md#adr-007--retain-minifi-java-for-the-verified-integration).

## Deployment state machine
The implemented test path is `DRAFT → PUBLISHED → PENDING → DISPATCHED → ACKNOWLEDGED → APPLIED`.
A negative ACK transitions the deployment to `FAILED`. A partial unique index permits one
active delivery per eligible agent. Timeout, staged rollout, and rollback are planned.

## Scale and availability
Use stateless API/C2 instances behind a reverse proxy. PostgreSQL is source of truth; Redis is
only queue/cache. Use jittered heartbeat intervals and exponential backoff. Batch bulk rollout.
Test 1000 agents, reconnect storms, large artifacts and database failover.

## Non-goals for v1
Inbound edge control, a generic remote shell, unbundled NiFi extensions, and
exactly-once guarantees across external systems are outside the current scope.
