# Security requirements

Compose publishes the UI and API on host loopback. PostgreSQL, Redis and SeaweedFS are
reachable inside the Compose network, where other containers are trusted. Use the disposable
defaults only on a developer machine. Keep real credentials in untracked local configuration.

Local MiNiFi C2 uses HTTP. The reported agent identifier and metadata are unverified, so a
client with access to the API can impersonate an agent. The ACK matches its operation ID and
the reported agent ID when supplied. That reported ID is unauthenticated. Java failure ACKs may
supply just the operation ID. The optional probe issues only a read-only manifest request. The adapter bounds and validates C2 bodies and persists only selected
inventory fields and the ACK state.

The API has no allowed targets by default when run outside the development Compose
stack. Compose permits its bundled Java and C++ test IDs if there are no explicit IDs.
Set `MINIFI_ENABLE_COMPOSE_TEST_TARGETS=false` to turn off those defaults, or set
explicit target IDs using `MINIFI_FLOW_AGENT_IDS` or the legacy singular setting.
Inventory membership alone grants no deployment permission. Reported manifest components
are checked for compatibility and the IDs constrain delivery in the local stack.
Runtime and manifest checks use claims from the agent. Production deployment requires authenticated
enrollment, scoped artifact access, mTLS and authenticated management operations.

The downloadable artifact can authorize filesystem access and interaction with services
reachable from the device. Run it with least-privilege device permissions. Java
`ExecuteProcess` and `ExecuteStreamCommand`, and C++ `ExecuteProcess` and `ExecuteScript`,
require `MINIFI_ALLOW_EXECUTION_PROCESSORS=true` to deploy. Enable it only for trusted
targets and operators. Other component behavior depends on its deployment environment
and properties. Sensitive descriptor values are rejected before
draft persistence. Parameter contexts and remote secret distribution are pending.

The optional NiFi overlay uses unauthenticated HTTP and publishes its UI and API on
host loopback. Use it in a trusted local Compose network. The backend connects only
to its server-configured NiFi origin and does not follow redirects. The browser selects a port
UUID from that server's live catalog. Production Site-to-Site needs authenticated TLS
and authorized port access.

Before production, implement the following.
1. TLS reverse proxy; no public plaintext endpoints.
2. Unique client certificate or cryptographic identity per agent.
3. Validate agent identity and class authorization on every C2 request.
4. Short-lived scoped artifact tokens and SHA-256 verification.
5. Encrypt sensitive flow parameters; never commit secrets to Git.
6. Integrate a secrets manager such as OpenBao for secrets/certificates.
7. OIDC, RBAC, audit trail and administrator MFA.
8. Sign artifacts and verify signatures on edge.
9. Restrict processor capabilities; disable arbitrary shell execution by default.
10. Least-privilege OS service accounts and filesystem ACLs.
11. Encrypted backups, restore tests and retention policy.
12. Pin container images by digest and scan dependencies.

Outbound-only is not sufficient security by itself.
