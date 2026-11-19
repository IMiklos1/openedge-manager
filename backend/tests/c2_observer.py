"""Forward real MiNiFi traffic to the API and retain selected test evidence in memory."""

import json
from collections import deque
from hashlib import sha256
from typing import Literal
from urllib.error import HTTPError
from urllib.request import Request as UpstreamRequest
from urllib.request import urlopen

from fastapi import FastAPI, Request, Response
from starlette.concurrency import run_in_threadpool

app = FastAPI()
observations = deque(maxlen=64)
received_data = deque(maxlen=64)


def forward(operation, body=None, headers=None):
    request = UpstreamRequest(
        f"http://api:8000/c2-protocol/{operation}", data=body, headers=headers or {},
    )
    try:
        response = urlopen(request, timeout=5)
    except HTTPError as error:
        response = error
    with response:
        return response.status, response.headers.get("Content-Type"), response.read()


@app.get("/observations")
async def get_observations():
    return list(observations)


@app.get("/test-data")
def received():
    return list(received_data)


@app.post("/test-data", status_code=204)
async def receive(request: Request):
    body = await request.body()
    received_data.append({"sha256": sha256(body).hexdigest(), "labels": request.headers.get("x-oem-test")})
    return Response(status_code=204)


@app.post("/c2-protocol/{operation}")
async def observe(operation: Literal["heartbeat", "acknowledge"], request: Request):
    body = await request.body()
    headers = {key: request.headers[key] for key in ("Content-Type", "Content-Encoding") if key in request.headers}
    status, media_type, result = await run_in_threadpool(forward, operation, body, headers)
    if operation == "heartbeat" and status == 200:
        payload = json.loads(body)
        agent = payload["agentInfo"]
        manifest = agent.get("agentManifest") or {}
        device = payload.get("deviceInfo") or {}
        system = device.get("systemInfo") or {}
        network = device.get("networkInfo") or {}
        flow = payload.get("flowInfo") or {}
        observations.append({
            "kind": "heartbeat",
            "identity": {
                "id": agent["identifier"],
                "agent_class": agent.get("agentClass"),
                "runtime": manifest.get("agentType"),
                "runtime_version": manifest.get("version"),
                "hostname": network.get("hostname"),
                "os_name": system.get("operatingSystem"),
                "architecture": system.get("machineArch"),
            },
            "operations": json.loads(result)["requestedOperations"],
            "flow": {
                "flowId": flow.get("flowId"),
                "processorStatuses": [
                    {"id": processor["id"], "flowFilesIn": processor.get("flowFilesIn", 0)}
                    for processor in (flow.get("processorStatuses") or [])
                ],
            },
        })
    elif operation == "acknowledge" and status == 204:
        payload = json.loads(body)
        observations.append({
            "kind": "acknowledgement",
            "agent_id": (payload.get("agentInfo") or {}).get("identifier"),
            "operation_id": payload["operationId"],
            "state": payload["operationState"]["state"],
        })
    return Response(result, status_code=status, media_type=media_type)


@app.get("/c2-protocol/configuration/{operation_id}")
async def observe_configuration(operation_id: str):
    status, media_type, result = await run_in_threadpool(forward, f"configuration/{operation_id}")
    if status == 200:
        observations.append({"kind": "configuration", "operation_id": operation_id, "sha256": sha256(result).hexdigest()})
    return Response(result, status_code=status, media_type=media_type)
