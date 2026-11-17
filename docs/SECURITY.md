# Security requirements

Compose is local-development only. Before production:
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
