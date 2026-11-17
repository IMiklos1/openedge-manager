# Implementation plan

## Phase 0 — Runtime spike (2–3 weeks)
Pin MiNiFi C++ release; build/test Windows x64, Linux x64 and ARM64; verify candidate processors;
build C2 contract harness; test offline continuation and reconnect.
Exit: supported runtime/build matrix and verified processor list.

## Phase 1 — Control plane MVP (3–5 weeks)
Complete migrations, agent identity/inventory, classes/capabilities, C2 adapter, contract tests,
artifact store and digest verification.
Exit: agents check in outbound and receive a harmless test operation.

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
