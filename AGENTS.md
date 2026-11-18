# AGENTS.md — OpenEdge Manager

> Instructions for AI coding agents working in this repository. Read this file before making changes. If nested `AGENTS.md` files exist, follow their more specific instructions for the corresponding directories.

## Mission and scope

Build **OpenEdge Manager (OEM)**, an open-source-first alternative to Cloudera Edge Manager, capable of managing **100–1,000 edge agents** on **Windows and Linux**, across mixed CPU architectures and hardware. Agents must initiate **outbound-only** connections to the control plane.

Core capabilities:
- Fleet inventory, enrollment, identity, heartbeat, health, status, tagging and diagnostics.
- Advanced independent visual Flow Designer, processor catalog, typed properties, validation, versioning and compilation.
- Immutable flow artifacts, targeting, deployment, acknowledgements, rollout status, failure handling and rollback.
- Integrations: MQTT, Modbus, OPC UA, HTTP(S), files, Kafka, SQL and TCP, **subject to verified support per runtime, extension, OS and architecture**.
- Security, auditability, observability, reproducible development and automated integration tests.

**Do not treat the starter scaffold as a finished product.** Prefer small, fully tested vertical slices over large amounts of mock functionality.

## Working agreement

1. **Inspect first.** Read `README.md`, this file, relevant files under `docs/`, `docker-compose.yml`, and the affected source code. Inspect `git status` and recent commits. The actual repository is authoritative; the initial scaffold may have changed.
2. **Plan briefly, then code.** For nontrivial tasks, outline approach, acceptance criteria and risks; then implement. Do not stop after producing a plan unless blocked.
3. **Preserve user work.** Never discard uncommitted changes or force-push. Work on a feature branch and submit a reviewable PR when supported.
4. **Keep scope tight.** Avoid unrelated refactors, dependency churn and speculative abstractions.
5. **Prove functionality.** An API endpoint, UI button or Docker service definition is not proof of working functionality. Test the end-to-end behavior.
6. **Report accurately.** Clearly separate implemented, tested, simulated, partially implemented and unverified features. Never claim Docker or real-agent tests passed if they were not run.
7. **Document as you go.** Update README, architecture, API, security and implementation plan when behavior or dependencies change.
8. **Ask for approval** before destructive database/volume operations, changes to production infrastructure, publishing, spending money, exposing services publicly or making irreversible security decisions.
9. **Communicate with the owner in Hungarian.** Code identifiers and technical documentation should normally be in English.

## Initial repository layout

The original starter contained:
- `backend/`: FastAPI, SQLAlchemy, management APIs, initial models, C2 adapter stub, compiler stub.
- `frontend/`: React, TypeScript, React Flow visual designer scaffold.
- `docker-compose.yml`: PostgreSQL, Redis, S3-compatible object storage, backend, frontend.
- `docs/`: architecture, API, security, decisions and implementation plan.
- `examples/`: demonstration flow.

Verify these paths and their current contents before relying on them.

### Known original gaps — verify before assuming they remain

- `/api/v1/agents/{id}/heartbeat` was an OEM development endpoint, **not** the official Apache MiNiFi C++ C2 wire protocol.
- The C2 adapter was an interface/stub, not a proven protocol implementation.
- The flow compiler did not generate verified MiNiFi C++ configuration.
- Deployment initially stored metadata without actually delivering or applying a flow.
- The processor catalog was illustrative rather than verified against a pinned runtime build.
- Modbus/OPC UA may require custom extensions or gateways; Kafka/SQL and other processors require exact-build verification.
- Production authentication, RBAC, mTLS, artifact integrity, secrets handling and auditing were incomplete.

Do not paper over these gaps with mock responses.

## Architecture principles

### Control plane and agents

- The control plane owns agent inventory, flow versions, immutable artifacts, deployments, audit events and user permissions.
- Edge devices **only initiate outbound connections**. No control-plane-to-agent inbound port is required.
- Agents must be uniquely enrolled and authenticated; use TLS and plan for mTLS, certificate rotation and revocation.
- Support intermittent networks, restarts, duplicated messages, retries and delayed acknowledgements.
- Use idempotent commands and persist state transitions.
- Separate small C2 messages from large artifact downloads; use scoped, short-lived authenticated URLs or equivalent secure delivery.
- Do not trust agent-supplied metadata or C2 payloads.

### Apache MiNiFi C++ integration

- **Pin an exact Apache MiNiFi C++ release/build** and document a tested OS/architecture matrix.
- Check the official source and documentation for that **exact** version; do not assume Java MiNiFi or NiFi processors/configuration are compatible.
- Implement the real supported C2 protocol, including heartbeat, command delivery and acknowledgement semantics required by the chosen release.
- Keep OEM management APIs separate from MiNiFi C2 endpoints.
- Test C2 messages against a **real running agent**, not just fabricated payloads.
- Validate actual processor availability, properties, relationships, scheduling and configuration schema.
- Record unsupported capabilities explicitly.

### Flow Designer and compiler

- Store an OEM-owned, **versioned canonical flow representation** independent of any specific agent runtime.
- Validate node IDs, processor types, required and typed properties, relationships, connections, and runtime compatibility.
- Compile deterministically to the **pinned MiNiFi C++ configuration format**.
- Produce actionable validation errors linked to specific nodes, properties or edges.
- Never silently drop unsupported nodes or unknown properties.
- Store immutable flow versions and the compiler/runtime version used to produce each artifact.

### Deployment lifecycle

- Define and document an explicit state machine, including at least validation, queueing, delivery, acknowledgement, application, failure, timeout and rollback.
- **Delivery is not acknowledgement; acknowledgement is not successful application.**
- Track status **per target agent**, including immutable artifact version, initiation time, actor and result.
- Handle duplicate delivery/ACK, offline agents, superseding deployments and retry safely.
- Do not claim rollback until a known-good version can actually be restored and verified.

## Docker Compose and local integration environment

The development environment must eventually include:
- FastAPI backend and React frontend.
- PostgreSQL and Redis.
- An S3-compatible object store behind a replaceable storage abstraction.
- At least **one real MiNiFi C++ test agent**, ideally under a Compose profile.
- A simple HTTP receiver for `GetFile -> InvokeHTTP` end-to-end verification.
- Optional additional agents and MQTT broker under an integration-test profile.

**Important object-storage issue:** The original `minio/minio:latest` image failed to pull. Do not reintroduce it. Verify the current availability, maintenance, license, supported platforms and exact image tag/digest of any replacement. Do not assume a proposed fork or registry tag is valid without verification.

- Pin infrastructure images; avoid floating `latest` tags.
- Use health checks and appropriate dependency readiness handling.
- Do not mount host configuration paths over critical container defaults without checking the exact image layout.
- Keep local secrets in `.env` or secret stores; commit only safe `.env.example` defaults.
- Preserve persistent volumes unless deletion is explicitly approved.
- Document commands for **Windows PowerShell** as well as portable shell usage where useful.
- Prefer a real end-to-end smoke test over a green `docker compose config` alone.

## Backend rules

- Follow the existing FastAPI architecture; keep route handlers thin and domain logic testable.
- Use explicit Pydantic request/response models and consistent API errors.
- Use transactions for multi-step state changes and migrations for schema evolution.
- Validate all inputs and enforce authentication/authorization on management operations.
- Use pagination/filtering for fleet and history APIs; index important lookup paths.
- Make background processing retry-safe, observable and restart-tolerant.
- Do not block async endpoints with synchronous network or disk I/O.
- Add unit tests for domain logic and integration tests for persistence/C2/deployments.
- Keep API versioning explicit, currently `/api/v1` where applicable.

## Frontend rules

- Use strict TypeScript types for flows, nodes, processors, API payloads and deployment states.
- Keep API calls in a shared client layer.
- Provide loading, empty, error, permission-denied and success states.
- Surface backend/compiler validation errors in the relevant flow node/property UI.
- Protect users against accidental loss of unsaved flow edits.
- Support keyboard-accessible controls where practical.
- Avoid presenting simulated telemetry or deployment success as real data.
- Add component or end-to-end tests for important user journeys.

## Security baseline

- Never commit credentials, private keys, access tokens or production data.
- Never log secrets or embed them in frontend bundles.
- Use TLS outside isolated local development; plan mTLS device identity.
- Use least-privilege service accounts, scoped object-storage access and artifact integrity verification.
- Validate and constrain uploaded files, paths, C2 messages and generated configurations.
- Enforce RBAC and audit security-sensitive management actions.
- Plan for token/certificate rotation, revocation, replay protection and rate limiting.
- Do not disable certificate verification, authorization or safe defaults just to make tests pass.
- Clearly isolate any development-only insecure mode.

## Tests and definition of done

Before claiming completion, run the relevant available checks:
- Backend tests and configured lint/type checks.
- Frontend typecheck, lint/tests and production build.
- JSON/YAML validation and `docker compose config`.
- Docker image pulls/builds and service health checks **if Docker is available**.
- Real MiNiFi C++ C2 heartbeat/ACK and flow execution tests **when that capability is in scope**.

For a feature to be complete, it must have:
1. Defined behavior and error cases.
2. Validated inputs and appropriate security.
3. Working persistence/state transitions if applicable.
4. Automated tests and an honest account of what actually ran.
5. Updated documentation and clear known limitations.

If Docker, external registries, network access or Windows execution are unavailable, state the limitation. Never substitute a static test for a real integration test while describing them as equivalent.

## Documentation to maintain

- `README.md`: setup, supported features, current limitations and troubleshooting.
- `docs/ARCHITECTURE.md`: component boundaries and data/control flows.
- `docs/API.md`: endpoint contracts and error semantics.
- `docs/SECURITY.md`: trust model, device identity, secrets and artifact integrity.
- `docs/IMPLEMENTATION_PLAN.md`: priorities, progress, test status and blockers.
- `docs/DECISIONS.md`: significant design decisions and trade-offs.

Use status labels such as **implemented**, **experimental**, **planned** and **unsupported**.

## Priority order

Unless the owner changes priorities:

1. Repair reproducible Docker Compose setup and replace broken/unverified images.
2. Add a pinned, real MiNiFi C++ test agent to Compose.
3. Implement and verify actual C2 heartbeat, agent registration and acknowledgement.
4. Implement a versioned canonical flow model and real deterministic MiNiFi compiler.
5. Implement deployment delivery, per-agent status, retries and verified application.
6. Prove `GetFile -> InvokeHTTP` against a test receiver using a real agent.
7. Add Windows/Linux packaging and supported architecture testing.
8. Extend the advanced Flow Designer and verified processor/protocol catalog.
9. Harden security, observability, multi-user features and 100–1,000 agent scaling.

Avoid UI polish and large catalog expansions while the C2/deployment path is still a stub.

## Agent session checklist

At the beginning:
1. Read this file and the relevant docs.
2. Inspect `git status --short --branch` and recent commits.
3. Verify the current repository state and existing test commands.
4. Identify the smallest valuable incomplete vertical slice.
5. State a short plan and acceptance criteria, then implement.

At the end, report in **Hungarian**:
- What changed, including relevant files.
- Which tests/commands actually ran and their results.
- What remains unverified or blocked.
- Any security/compatibility implications.
- The recommended next task.
- PR/commit reference, if one was created.

**North star:** a genuinely functional, secure and testable edge-management platform—not a convincing-looking collection of stubs.
