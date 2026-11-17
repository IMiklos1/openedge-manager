# Architecture decisions

- ADR-001: OEM JSON DSL is canonical; runtime config is generated. This keeps the designer
  independent and allows future runtimes.
- ADR-002: edge initiates all control-plane connections over TLS. This supports outbound-only
  networks but requires async command delivery, jitter, ACK and retries.
- ADR-003: MiNiFi C++ is the initial runtime for Windows x64, Linux x64 and Linux ARM64.
  Processor availability is verified per exact build.
- ADR-004: Modbus and OPC UA are not assumed to exist in stock runtime; evaluate custom
  processors versus a local protocol gateway.
