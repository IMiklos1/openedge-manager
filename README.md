# OpenEdge Manager (OEM)

Self-hosted development foundation for edge fleet and flow management with an independent
React Flow designer and outbound Apache MiNiFi Java and C++ C2.

## Quick start from my VS Code

```powershell
docker compose --profile agent up -d --build
```

Check logs:
```powershell
docker compose --profile agent ps
docker compose --profile agent logs -f minifi-agent-01 minifi-cpp
```

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

The `agent` profile starts both pinned Apache MiNiFi images from
[`compose.minifi.yaml`](compose.minifi.yaml): Java 2.12.0 as `oem-test-agent-01`
and C++ 1.1.0 as `oem-test-agent-cpp`. Both use class `openedge-test` and send
full, uncompressed C2 heartbeats to the local API every five seconds without publishing
agent ports. The default Compose configuration permits deployment to both test agents.
The first full C2 heartbeat makes a compatible agent selectable in Flow Manager.
The C2 routes are documented in [the API specification](docs/API.md). Omit
`--profile agent` if you only need the control plane.

On Bash, use `test -f .env || cp .env.example .env` and the same Compose commands.
`docker compose --profile agent down` stops the stack and keeps its named volumes.

## Create and deploy the test flow

Use a disposable local agent. A deployment replaces its active flow. From PowerShell:

```powershell
docker compose --profile agent up --build -d --wait
```

Open **Flow Manager** at `http://127.0.0.1:5173`. Select **Load test flow**. Click a
processor to edit its properties, scheduling, comments and relationships. Select a
connection to configure its name, relationship and queue. Create and configure controller
services from the designer's selector when a component needs one. Save the draft and
select `oem-test-agent-01` under **Target agent**. Click **Publish and deploy** to compile
the saved revision and queue the update. You can also publish it separately and then
click **Deploy flow**. Registered agents that cannot receive a deployment appear in
the list with a reason.
`ACKNOWLEDGED` records the agent's C2 result. `APPLIED` appears after a later heartbeat
reports the published digest as the running flow. The test flow generates a one-byte FlowFile
and sends it to LogAttribute.

The same flow is available as [a draft request](examples/minifi-java-test-flow.json).
To run it against a fresh project through the API:

```powershell
$api = "http://127.0.0.1:8000/api/v1"
$body = Get-Content -Raw examples/minifi-java-test-flow.json
$draft = Invoke-RestMethod -Uri "$api/flows" -Method Post -ContentType "application/json" -Body $body
Invoke-RestMethod -Uri "$api/flows/$($draft.id)/publish" -Method Post
$deployment = Invoke-RestMethod -Uri "$api/deployments" -Method Post -ContentType "application/json" -Body (
    @{ flow_id = $draft.id; agent_id = "oem-test-agent-01" } | ConvertTo-Json
)
Invoke-RestMethod -Uri "$api/deployments/$($deployment.id)"
docker compose --profile agent logs --tail 75 minifi-agent-01
```

Repeat the status request as the agent checks in. The example uses a fixed draft ID. Use the
designer or change the example ID for another draft. The API applies Alembic migrations at
startup and preserves existing records. Open a saved flow to continue editing it. Each
successful save creates a revision and the **Versions** list opens historical revisions
read-only. Published revisions remain available for explicit redeployment. **Edge Agents**
shows recent heartbeats and class activity. **Deployments** shows persisted outcomes and ACKs
with an agent and status filter.

## Send FlowFiles to the project's NiFi

The `compose.nifi.yaml` overlay runs Apache NiFi 2.12.0 inside the same project.
Start NiFi with both edge runtimes from PowerShell or Bash:

```powershell
docker compose -f docker-compose.yml -f compose.minifi-cpp.yaml -f compose.nifi.yaml --profile agent --profile cpp up --build -d --wait
```

1. Open [NiFi](http://127.0.0.1:8080/nifi/). Add an **Input Port** to the root group,
   enable remote access, connect it to your downstream NiFi flow and start it.
2. Open [Flow Manager](http://127.0.0.1:5173). Add a **Remote Process Group** and select
   the NiFi Input Port by name and UUID. Use **Refresh Input Ports** after changing the NiFi flow.
3. Connect a processor's outgoing relationship to the Remote Process Group. Save,
   select a compatible agent and choose **Publish and deploy**. The agent initiates
   HTTP Site-to-Site and NiFi takes over processing at the Input Port.

The selected UUID is stored in the flow revision. Add a Remote Process Group for each
target port. Publication checks that NiFi still advertises the UUID.
`OEM_NIFI_PORT` changes the host UI port. Agents on the Compose network use
`http://nifi:8080`. The NiFi flow, state and repositories use named volumes.
Allow time and disk space for the first startup and extension extraction.
[Local security boundary](docs/SECURITY.md)

Stop the integrated stack with the same file and profile arguments and the `down`
command. If the picker is empty, check the port's remote-access setting and that
the API was started with the NiFi overlay.

## Run Java and C++ together

Start both agents with `docker compose --profile agent up -d --build`.
To run the control plane with only the C++ agent, use `--profile cpp` instead.

In **Flow Manager**, choose **MiNiFi C++** under **Flow runtime** and load the test
flow. The C++ palette includes GenerateFlowFile, UpdateAttribute and LogAttribute with
their native properties. After the first full heartbeat the new C++ target appears as
`oem-test-agent-cpp`. Save, select it, and choose **Publish and deploy**. Java and C++
agents are both visible, and deployment requires the flow and target to use the same runtime.
Existing flows use Java unless their saved revision specifies C++.

The [C++ starter script](agents/minifi-cpp/start.sh) shows the native
`minifi.properties` C2 settings. For a separate device use its own allowed ID, a
reachable C2 origin, and a matching pinned runtime and manifest. Java uses its
`bootstrap.conf` settings described below.

If native Windows MiNiFi C++ 1.1.0 sends an invalid UTF-8 hostname and receives a
C2 HTTP 422, create `conf\minifi.properties.d\99-oem-c2.properties` with the following
setting and restart the agent:

```properties
nifi.c2.root.classes=AgentInformation,FlowInformation,AssetInformation
```

This workaround omits device metadata (including hostname, OS, and architecture)
but keeps agent identity, manifest, and flow reporting. Keep `nifi.c2.full.heartbeat=true`
so OEM can detect the runtime and components.

## Run the automated smoke tests

Use a fresh Compose project so the suite observes a new C2 operation and acknowledgement.
Run these commands from the repository root in PowerShell with Docker Desktop in Linux container mode.

```powershell
$smokeProject = "openedge-smoke-" + [guid]::NewGuid().ToString("N").Substring(0, 8)
$env:MINIFI_PROBE_AGENT_ID = "oem-smoke-agent-01"
$env:MINIFI_FLOW_AGENT_ID = "oem-smoke-agent-01"
$env:OEM_API_PORT = "0"
$env:OEM_UI_PORT = "0"
try {
    docker compose -p $smokeProject --profile smoke config --quiet
    if ($LASTEXITCODE -ne 0) { throw "Compose config failed ($LASTEXITCODE)." }
    docker compose -p $smokeProject --profile smoke up --build --exit-code-from smoke
    if ($LASTEXITCODE -ne 0) { throw "Compose smoke tests failed ($LASTEXITCODE)." }
} finally {
    docker compose -p $smokeProject --profile smoke down
    Remove-Item Env:MINIFI_PROBE_AGENT_ID, Env:MINIFI_FLOW_AGENT_ID, Env:OEM_API_PORT, Env:OEM_UI_PORT
}
```

On Bash:

```bash
smoke_project="openedge-smoke-$(date +%s)-$$"
MINIFI_PROBE_AGENT_ID=oem-smoke-agent-01 MINIFI_FLOW_AGENT_ID=oem-smoke-agent-01 OEM_API_PORT=0 OEM_UI_PORT=0 \
  docker compose -p "$smoke_project" --profile smoke up --build --exit-code-from smoke
smoke_exit=$?
docker compose -p "$smoke_project" --profile smoke down
test "$smoke_exit" -eq 0
```

Port `0` asks Docker for available loopback ports. The tests run inside the Compose network.
The `smoke` profile starts `oem-smoke-agent-01` from the same pinned Java image as the
`agent` profile. A test-only HTTP observer forwards its real traffic to the backend. The suite
compares the observed heartbeat with the API and PostgreSQL, then matches the command ID in the
heartbeat response to the Java ACK and persisted outcome. It also checks UI/API readiness, Redis,
and signed S3 object I/O. The suite also publishes a flow, verifies the downloaded bytes against
the SHA-256 digest, and waits for the real agent to report that LogAttribute received FlowFiles. The catalog
check compares every component with the real C2 manifest. The file integration test checks
that GetFile, UpdateAttribute, RouteOnAttribute and InvokeHTTP deliver matching bytes
and a dynamic header to the local HTTP receiver.
A successful run prints `MiNiFi applied <digest> and LogAttribute received a FlowFile`.

For smoke-test diagnostics before cleanup, run
`docker compose -p $smokeProject --profile smoke logs --tail 100 api c2-observer minifi-smoke-agent smoke`.
Test results and platform coverage are in the [implementation plan](docs/IMPLEMENTATION_PLAN.md).

### Mixed-runtime smoke tests

With a fresh Compose project, set these values in PowerShell:

```powershell
$project = "openedge-dual-" + [guid]::NewGuid().ToString("N").Substring(0, 8)
$env:MINIFI_PROBE_AGENT_ID = "oem-smoke-agent-01"
$env:MINIFI_FLOW_AGENT_ID = "oem-smoke-agent-01"
$env:MINIFI_FLOW_AGENT_IDS = "oem-test-agent-cpp"
$env:OEM_CPP_C2_ORIGIN = "http://c2-observer:8001"
$env:OEM_API_PORT = "0"
$env:OEM_UI_PORT = "0"
try {
    docker compose -f docker-compose.yml -f compose.minifi-cpp.yaml -p $project --profile smoke up --build --exit-code-from smoke
    if ($LASTEXITCODE -ne 0) { throw "Mixed smoke tests failed ($LASTEXITCODE)." }
} finally {
    docker compose -f docker-compose.yml -f compose.minifi-cpp.yaml -p $project --profile smoke down
    Remove-Item Env:MINIFI_PROBE_AGENT_ID, Env:MINIFI_FLOW_AGENT_ID, Env:MINIFI_FLOW_AGENT_IDS
    Remove-Item Env:OEM_CPP_C2_ORIGIN, Env:OEM_API_PORT, Env:OEM_UI_PORT
}
```

Add `-f compose.nifi.yaml` before `-p` in both the startup and cleanup commands to include
the real Site-to-Site tests. They create an Input Port and downstream processor in
NiFi, deploy a flow to each agent and check the forwarded payload by SHA-256.

The suite verifies that both runtimes check in, then publishes and deploys different
C++ revisions and waits for processing metrics, download digests and C2 acknowledgements.

On Bash:

```bash
project="openedge-dual-$(date +%s)-$$"
MINIFI_PROBE_AGENT_ID=oem-smoke-agent-01 MINIFI_FLOW_AGENT_ID=oem-smoke-agent-01 \
  MINIFI_FLOW_AGENT_IDS=oem-test-agent-cpp OEM_CPP_C2_ORIGIN=http://c2-observer:8001 OEM_API_PORT=0 OEM_UI_PORT=0 \
  docker compose -f docker-compose.yml -f compose.minifi-cpp.yaml -p "$project" --profile smoke up --build --exit-code-from smoke
result=$?
docker compose -f docker-compose.yml -f compose.minifi-cpp.yaml -p "$project" --profile smoke down
test "$result" -eq 0
```

## Verify the workspace in Chromium

Use disposable agents. The browser test creates draft revisions, configures and references
JSON controller services, reads the saved graph, and deploys the two revisions to selected
agents. It verifies that an ineligible inventory entry is visible and disabled. The fleet
profile adds a second independent agent for this test. Run with the default test target
settings and a fresh Compose project.

```powershell
docker compose --profile agent --profile fleet up --build -d --wait
$env:OEM_BROWSER_SECOND_AGENT = "oem-test-agent-02"
$env:OEM_CHROMIUM = "C:\Program Files\Google\Chrome\Application\chrome.exe"
$env:OEM_BROWSER_URL = "http://127.0.0.1:5173"
npm --prefix frontend ci
npm --prefix frontend run test:browser
docker compose --profile agent --profile fleet down
```

On Linux with Chromium installed:

```bash
docker compose --profile agent --profile fleet up --build -d --wait
npm --prefix frontend ci
OEM_BROWSER_SECOND_AGENT=oem-test-agent-02 OEM_CHROMIUM=/usr/bin/chromium npm --prefix frontend run test:browser
docker compose --profile agent --profile fleet down
```

To send both revisions to one local target, omit `OEM_BROWSER_SECOND_AGENT` and the
`fleet` profile. The browser test defaults to `oem-test-agent-01` and the UI on port 5173.
To verify both runtimes, start the mixed stack and set
`OEM_BROWSER_CPP_AGENT=oem-test-agent-cpp` before running the same browser test.

### Targeting a connected agent

Compose defaults to the bundled Java IDs and `oem-test-agent-cpp`. To
target other devices, set `MINIFI_FLOW_AGENT_IDS` to a comma-separated list of the
allowed IDs and recreate the API container with `docker compose up -d api`. The
singular `MINIFI_FLOW_AGENT_ID` remains supported. Explicit IDs replace the Compose
defaults. Set `MINIFI_ENABLE_COMPOSE_TEST_TARGETS=false` to disable the defaults
when you have no explicit targets.
For a Java agent on a separate machine to appear as a deployment target, configure its
outbound C2 base URL and identifier, enable its full heartbeat, and use a trusted
network and the same pinned runtime components. Compose binds its control plane to
loopback for development. Production access needs authenticated management and agent
ingress. [C2 API](docs/API.md#minifi-java-2120-and-c-110-c2) · [Security](docs/SECURITY.md)

For the native Java distribution, set these properties in `conf/bootstrap.conf` with
your own target ID and a C2 endpoint already reachable from the device. Use TLS outside
an isolated development network.

```properties
c2.enable=true
c2.agent.identifier=lab-edge-03
c2.agent.class=lab
c2.full.heartbeat=true
c2.request.compression=none
c2.rest.path.base=https://oem.example.org/c2-protocol
c2.rest.path.heartbeat=/heartbeat
c2.rest.path.acknowledge=/acknowledge
```

Add `lab-edge-03` to the server's allowed IDs. The agent opens all connections, including
the download of the compiled `flow.json.raw` contents.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| Docker is unreachable | Run `docker version`. Start Docker Desktop and switch to Linux containers if needed. |
| Port already in use | Set `OEM_API_PORT` or `OEM_UI_PORT` in `.env`, then use the corresponding port in your browser or PowerShell. |
| Build cannot verify a corporate proxy certificate | Set `$env:OEM_BUILD_CA_FILE = 'C:\\path\\to\\trusted-ca-bundle.pem'` to a PEM bundle with your trusted corporate CA and standard roots. Run `docker compose -f docker-compose.yml -f compose.build-ca.yml --profile agent up --build -d --wait`. Configure Docker Desktop's registry trust separately if the error occurs while pulling an image. |
| API health fails | Run `docker compose logs postgres api`. The API uses the same `POSTGRES_*` values as PostgreSQL. A previously initialized volume retains its original roles and passwords. Restore the matching settings or rotate the database credentials in PostgreSQL. |
| Agent is missing or has no ACK | Run `docker compose --profile agent logs --tail 100 minifi-agent-01 api`. Check the `agent` profile and `http://api:8000/c2-protocol/` URLs. Set `MINIFI_PROBE_AGENT_ID=oem-test-agent-01` before starting the API to enable one read-only manifest request. Use a fresh Compose project for another full smoke run. |
| Agent is listed but disabled in Flow Manager | Check its reason. Verify the allowed ID, the selected runtime, and the agent's full C2 manifest for Java 2.12.0 or C++ 1.1.0. After changing target settings, recreate the API container. |
| Upgrading from MinIO/Silo | Compose now provisions the S3 bucket in the new `s3data` volume. The old `miniodata` volume remains on disk. Copy any existing objects through an S3 client using their original service before retiring that volume. |

## Scope

The designer exposes the 117 processors and 47 controller services shipped with the
pinned MiNiFi Java 2.12.0 image. Draft revisions and compiled artifacts persist in PostgreSQL.
External resources, sensitive values, custom extensions, runtime verification across all
processors and production fleet features have separate coverage and limitations.
[Catalog and runtime scope](docs/PROCESSOR_CATALOG.md)

Only the UI and API are published to host loopback. The stack uses local plaintext HTTP and
development-only credential defaults. See [architecture](docs/ARCHITECTURE.md) and
[security](docs/SECURITY.md) for the operating boundaries.
