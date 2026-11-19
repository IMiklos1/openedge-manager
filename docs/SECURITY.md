# Security requirements

Compose publishes the UI and API on host loopback. PostgreSQL, Redis and SeaweedFS are
reachable inside the Compose network, where other containers are trusted. Use the disposable
defaults only on a developer machine. Keep real credentials in untracked local configuration.

Local MiNiFi C2 uses HTTP. The reported agent identifier and metadata are unverified, so a
client with access to the API can impersonate an agent. The ACK matches its operation ID and
the reported agent ID when supplied. That reported ID is unauthenticated. Java failure ACKs may
supply just the operation ID. The optional probe issues only a read-only manifest request. The adapter bounds and validates C2 bodies and persists only selected
inventory fields and the ACK state.

Flow replacement is disabled by default. `MINIFI_FLOW_AGENT_ID` opts one disposable
agent into the test path. The compiler accepts only allowlisted processors and bounded literal properties. Expression Language, parameter
references and unrestricted regular expressions are excluded from the local compiler. The local download path is scoped to a dispatched operation. Agent IDs and
operation IDs provide correlation in this local setup. Production rollout requires
authenticated enrollment, scoped artifact access, and mTLS.

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
