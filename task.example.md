# Task: Architecture verification and first real end-to-end test

You are the lead engineer of OpenEdge Manager.

The first development PR has been merged. Before implementing more features, verify the actual repository state and the correctness of the edge runtime integration.

## Critical issue

The original architecture targeted Apache MiNiFi C++, but recent commits introduced Apache MiNiFi Java 2.12.0.

Investigate this architectural change.

1. Inspect the relevant commits, implementation, Docker Compose configuration, documentation, and tests.
2. Explain why MiNiFi Java was selected instead of MiNiFi C++.
3. Verify the actual runtime artifact, version, image availability, C2 protocol, and supported platforms.
4. Compare MiNiFi Java and MiNiFi C++ for:
   - Windows and Linux support
   - x86-64 and ARM64 compatibility
   - Memory and CPU requirements
   - C2 protocol support
   - Processor and extension availability
   - Long-term maintenance
5. Do not silently switch runtimes again. Record a recommendation and its trade-offs in docs/DECISIONS.md. If the decision is material or uncertain, request owner approval before migration.

## Implementation and verification

After inspecting the repository:

1. Fix any failing CI checks related to the merged PR.
2. Verify that the complete Docker Compose development stack builds and starts, if the environment permits.
3. Verify that a real MiNiFi agent sends C2 heartbeat messages.
4. Verify that the backend parses and persists the real heartbeat correctly.
5. Verify that an actual agent acknowledgement can be correlated with the originating command.
6. Add automated integration tests for these behaviors.
7. Document exact commands to reproduce the tests in Windows PowerShell.
8. Update the implementation plan and clearly mark verified versus unverified functionality.

## Acceptance criteria

- The selected agent runtime is clearly identified and justified.
- The backend receives real agent heartbeat messages.
- Agent identity and status are persisted correctly.
- C2 acknowledgements are correlated with the correct commands.
- CI checks are passing, or every failure is explicitly documented.
- Tests do not rely exclusively on fabricated C2 payloads.
- A developer can reproduce the verified tests locally.

Do not claim success if only unit tests or mocked agent responses passed.

Do not introduce unrelated features.

Create a pull request with implementation changes, evidence, exact test commands, limitations, and a Hungarian summary.