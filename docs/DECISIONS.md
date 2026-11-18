# Architecture decisions

- ADR-001: OEM JSON DSL is canonical; runtime config is generated. This keeps the designer
  independent and allows future runtimes.
- ADR-002: edge initiates all control-plane connections over TLS. This supports outbound-only
  networks but requires async command delivery, jitter, ACK and retries.
- ADR-003: MiNiFi Java is the integration runtime. Windows x64, Linux x64, and Linux ARM64
  are target platforms. See ADR-007 for the selection rationale and qualification status.
- ADR-004: Modbus and OPC UA are not assumed to exist in stock runtime; evaluate custom
  processors versus a local protocol gateway.
- ADR-005: use SeaweedFS 4.54 in single-node `weed mini` mode for local S3. Its
  [Apache-2.0 source](https://github.com/seaweedfs/seaweedfs/tree/4.54) and
  [published multi-architecture image](https://hub.docker.com/r/chrislusf/seaweedfs/tags)
  can be verified independently. Shared S3 integration and production topology remain separate work.
- ADR-006: verify the return path with MiNiFi Java 2.12.0's read-only `DESCRIBE MANIFEST`
  operation. Use a persisted operation ID to correlate ACKs without changing the edge flow.

## ADR-007 — Retain MiNiFi Java for the verified integration

**Status:** Recommended for the current integration. Revisit production runtime selection after
platform and workload qualification. Obtain owner approval before changing runtimes or making a
production platform commitment.

The original architecture targeted MiNiFi C++. The pre-PR commit
[`7dfd79f`](https://github.com/IMiklos1/openedge-manager/commit/7dfd79f) already configured
`apache/nifi-minifi:${MINIFI_VERSION}` with `MINIFI_VERSION=2.12.0`. PR #2 first implemented
the original C++ plan, then the owner specified the Java image already present in Compose.
[`6953ea0`](https://github.com/IMiklos1/openedge-manager/commit/6953ea0) restored that artifact
and implemented its Java C2 contract. [`9c17f9d`](https://github.com/IMiklos1/openedge-manager/commit/9c17f9d)
aligned the documentation. The selection followed the owner's requested integration target.
There was no comparative footprint or processor qualification in that decision.

| Dimension | Apache MiNiFi Java 2.12.0 | Apache MiNiFi C++ 1.1.0 |
| --- | --- | --- |
| Artifact | NiFi release tag `rel/nifi-2.12.0` at `19f4df8`. The official `minifi-2.12.0-bin.zip` and checksum are published. The pinned image ships OpenJDK 21.0.12.1 and reported `minifi-java` 2.12.0 over C2. | Independent release tag `rel/minifi-cpp-1.1.0` at `1a4b84e`. The official `apache/nifi-minifi-cpp:1.1.0` image was pulled and its binary reported 1.1.0. The Apache download index lists signed native packages. |
| Linux x86-64 and ARM64 | The image index has `linux/amd64` and `linux/arm64` manifests. OEM ran Linux amd64. Native use requires a compatible JVM and extensions for the OS and architecture. | Published native tarballs and Linux image manifests for x86-64 and ARM64. OEM ran the x86-64 image with an empty flow for the comparison below. |
| Windows x86-64 and ARM64 | The Java archive includes Windows launch scripts and service binaries. Qualify x86-64 with a supported JVM. Windows ARM64, the service wrapper and any native dependencies need their own qualification. Docker Desktop with Linux containers exercises the Linux distribution. | The 1.1.0 release publishes a Windows x86-64 MSI. The release index lists Windows x86-64 as its Windows binary target. OEM has yet to qualify native Windows or a Windows ARM64 build. |
| Memory and CPU | The image starts a JVM with a 256 MiB configured heap plus a bootstrap JVM. In the idle sample it used about 335 MiB process PSS and 1.3% of one CPU core. | Native executable with release-specific libraries and optional extensions. In the same idle sample it used about 56 MiB process PSS and 0.16% of one CPU core. |
| C2 | Outbound HTTP JSON with `requestedOperations`, command `identifier`, and an ACK carrying `operationId` and `operationState`. OEM verified the actual Java client's heartbeat and `DESCRIBE MANIFEST` return path. | RESTSender also supports outbound heartbeat and ACK. It serializes its own envelopes and accepts several response aliases, including `requested_operations`. A C++ integration needs its own wire-contract and command tests. |
| Processors and extensions | The tested image contains the MiNiFi standard and MQTT NARs. The release docs list `GetFile`, `InvokeHTTP`, `ListenTCP`, `ListenUDP`, and `ExecuteSQL`. Additional NiFi NARs need version and dependency checks. | Separate native processor and extension ecosystem. The inspected image includes standard processors and native MQTT, Kafka, SQL, OPC, AWS and Azure modules. Selection varies by build, platform and dependency. |
| Maintenance | Releases with Apache NiFi, so track NiFi, Java and NAR compatibility and advisories together. The upstream site lists 2.12.0 on 2026-09-13. | Separate release cadence and native build and dependency maintenance. The upstream site lists 1.1.0 on 2026-11-02. Published releases establish current activity for both projects. |

The image digests compared were `apache/nifi-minifi:2.12.0@sha256:ad599a28a8955ac6bc9b4f5839a767241e20efa406975aedd9c620c4f4a08578`
and `apache/nifi-minifi-cpp:1.1.0@sha256:647d0548f8411aeb7fc58def0666077c25f950ba85cf5cc58d4d28500b58e0cd`.
The idle sample used both images on the same Linux amd64 host with empty flows and C2 disabled.
It summed the agent and bootstrap processes' proportional set size from `/proc/*/smaps_rollup`
and sampled user and system CPU ticks from `/proc/*/stat` about 31 seconds apart. These are
observations of these builds. Sizing also needs startup, representative flows, I/O, and sustained
load measurements on target devices.

Keep Java 2.12.0 as the Compose and C2 baseline because it matches the owner-selected artifact
and has a verified return path. The Java footprint matters for constrained nodes. Before any
proposed migration, measure both runtimes with the intended flows, verify required processors and
extensions on Windows x86-64 and Linux x86-64/ARM64, and account for changes to packaging, flow
compilation, and C2 compatibility. Windows ARM64 remains an open platform choice.

Upstream sources are the [Apache release listing](https://nifi.apache.org/download/),
[Java artifact index](https://dlcdn.apache.org/nifi/2.12.0/),
[C++ artifact index](https://dlcdn.apache.org/nifi/nifi-minifi-cpp-1.1.0/),
[Java 2.12.0 agent guide](https://github.com/apache/nifi/blob/19f4df8e048e91d87d3e4967c69b1298f9dbe450/minifi/minifi-docs/src/main/markdown/minifi-java-agent-quick-start.md),
[Java C2 source](https://github.com/apache/nifi/tree/19f4df8e048e91d87d3e4967c69b1298f9dbe450/c2),
[C++ 1.1.0 build and extension guide](https://github.com/apache/nifi-minifi-cpp/blob/1a4b84eb8b53eebcf7c92d83f6ae818f440e33ee/README.md),
and [C++ C2 source](https://github.com/apache/nifi-minifi-cpp/tree/1a4b84eb8b53eebcf7c92d83f6ae818f440e33ee/libminifi/src/c2/protocols).
