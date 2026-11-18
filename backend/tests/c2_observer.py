"""Forward real MiNiFi traffic to the API and retain selected test evidence in memory."""

import json
from collections import deque
from typing import Literal
from urllib.error import HTTPError
from urllib.request import Request as UpstreamRequest
from urllib.request import urlopen

from fastapi import FastAPI, Request, Response
from starlette.concurrency import run_in_threadpool

app = FastAPI()
observations = deque(maxlen=64)


def forward(operation, body, headers):
    request = UpstreamRequest(
        f"http://api:8000/c2-protocol/{operation}", data=body, headers=headers,
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
