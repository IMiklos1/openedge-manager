# Architecture decisions

- ADR-001: OEM JSON DSL is canonical; runtime config is generated. This keeps the designer
  independent and allows future runtimes.
- ADR-002: edge initiates all control-plane connections over TLS. This supports outbound-only
  networks but requires async command delivery, jitter, ACK and retries.
- ADR-003: MiNiFi Java is the initial runtime for Windows x64, Linux x64 and Linux ARM64.
  Processor availability is verified per exact build.
- ADR-004: Modbus and OPC UA are not assumed to exist in stock runtime; evaluate custom
  processors versus a local protocol gateway.
- ADR-005: use SeaweedFS 4.54 in single-node `weed mini` mode for local S3. Its
  [Apache-2.0 source](https://github.com/seaweedfs/seaweedfs/tree/4.54) and
  [published multi-architecture image](https://hub.docker.com/r/chrislusf/seaweedfs/tags)
  can be verified independently. Shared S3 integration and production topology remain separate work.
- ADR-006: verify the return path with MiNiFi Java 2.12.0's read-only `DESCRIBE MANIFEST`
  operation. Use a persisted operation ID to correlate ACKs without changing the edge flow.
