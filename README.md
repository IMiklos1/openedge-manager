# OpenEdge Manager (OEM)

Self-hosted development foundation for edge fleet and flow management with an independent
React Flow designer and outbound Apache MiNiFi Java C2.

## Start on Windows with PowerShell

Start Docker Desktop with the Linux container engine and Compose v2. From the repository root:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
docker compose --profile agent config --quiet
docker compose --profile agent up --build -d --wait
docker compose ps
Invoke-RestMethod http://127.0.0.1:8000/api/v1/agents
```

- [Flow Designer](http://127.0.0.1:5173)
- [API documentation](http://127.0.0.1:8000/docs)
- [API readiness](http://127.0.0.1:8000/health)

The `agent` profile starts the official Apache MiNiFi Java 2.12.0 image pinned in
[`compose.minifi.yaml`](compose.minifi.yaml). It registers as
`oem-test-agent-01`, then checks in every five seconds without any published agent port.
The C2 routes are documented in [the API specification](docs/API.md). Omit
`--profile agent` if you only need the control plane.

On Bash, use `test -f .env || cp .env.example .env` and the same Compose commands.
`docker compose --profile agent down` stops the stack and keeps its named volumes.

## Run the automated smoke tests

Use a fresh Compose project so the suite observes a new C2 operation and acknowledgement.
In PowerShell:

```powershell
$smokeProject = "openedge-smoke-" + [guid]::NewGuid().ToString("N").Substring(0, 8)
$env:MINIFI_PROBE_AGENT_ID = "oem-test-agent-01"
$env:OEM_API_PORT = "0"
$env:OEM_UI_PORT = "0"
docker compose -p $smokeProject --profile smoke config --quiet
docker compose -p $smokeProject --profile smoke up --build --exit-code-from smoke
$smokeExit = $LASTEXITCODE
docker compose -p $smokeProject --profile smoke down
Remove-Item Env:MINIFI_PROBE_AGENT_ID, Env:OEM_API_PORT, Env:OEM_UI_PORT
if ($smokeExit -ne 0) { throw "Compose smoke tests failed (exit $smokeExit)." }
```

On Bash:

```bash
smoke_project="openedge-smoke-$(date +%s)-$$"
MINIFI_PROBE_AGENT_ID=oem-test-agent-01 OEM_API_PORT=0 OEM_UI_PORT=0 \
  docker compose -p "$smoke_project" --profile smoke up --build --exit-code-from smoke
smoke_exit=$?
docker compose -p "$smoke_project" --profile smoke down
test "$smoke_exit" -eq 0
```

Port `0` asks Docker for available loopback ports. The tests run inside the Compose network.
They check the Java agent's actual heartbeat and ACK, API readiness and the UI proxy, Redis, and a
signed S3 put/get/delete. Test results and platform coverage are in the
[implementation plan](docs/IMPLEMENTATION_PLAN.md).

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| Docker is unreachable | Run `docker version`. Start Docker Desktop and switch to Linux containers if needed. |
| Port already in use | Set `OEM_API_PORT` or `OEM_UI_PORT` in `.env`, then use the corresponding port in your browser or PowerShell. |
| Build cannot verify a corporate proxy certificate | Set `$env:OEM_BUILD_CA_FILE = 'C:\\path\\to\\trusted-ca-bundle.pem'` to a PEM bundle with your trusted corporate CA and standard roots. Run `docker compose -f docker-compose.yml -f compose.build-ca.yml --profile agent up --build -d --wait`. Configure Docker Desktop's registry trust separately if the error occurs while pulling an image. |
| API health fails | Run `docker compose logs postgres api`. The API uses the same `POSTGRES_*` values as PostgreSQL. A previously initialized volume retains its original roles and passwords. Restore the matching settings or rotate the database credentials in PostgreSQL. |
| Agent is missing or has no ACK | Run `docker compose --profile agent logs --tail 100 minifi-agent-01 api`. Check the `agent` profile and `http://api:8000/c2-protocol/` URLs. Set `MINIFI_PROBE_AGENT_ID=oem-test-agent-01` before starting the API to enable one read-only manifest request. Use a fresh Compose project for another full smoke run. |
| Upgrading from MinIO/Silo | Compose now provisions the S3 bucket in the new `s3data` volume. The old `miniodata` volume remains on disk. Copy any existing objects through an S3 client using their original service before retiring that volume. |

## Scope

The local stack stores agent inventory in PostgreSQL. Redis and SeaweedFS are provisioned
and tested for future queue and artifact integration. Flow editing and publication are starter
features, and deployment records are metadata. Runtime compilation, artifact delivery,
deployment execution, and production identity, RBAC, and mTLS are planned.

Only the UI and API are published to host loopback. The stack uses local plaintext HTTP and
development-only credential defaults. See [architecture](docs/ARCHITECTURE.md) and
[security](docs/SECURITY.md) for the operating boundaries.
