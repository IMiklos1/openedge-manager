"""Provision a disposable NiFi Input Port and an InvokeHTTP receiver flow."""

import argparse
import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4


def create_receiver(origin="http://nifi:8080"):
    def request(path, payload=None, method=None):
        body = None if payload is None else json.dumps(payload).encode()
        req = Request(f"{origin}/nifi-api{path}", data=body, method=method,
                      headers={"Content-Type": "application/json"})
        try:
            with urlopen(req, timeout=10) as response:
                return json.load(response)
        except HTTPError as exc:
            with exc:
                raise RuntimeError(f"NiFi fixture {path}: {exc.code} {exc.read().decode()}") from exc

    group = request("/flow/process-groups/root")["processGroupFlow"]["id"]
    name = f"OEM test Input Port {uuid4()}"
    port = request(f"/process-groups/{group}/input-ports", {
        "revision": {"version": 0},
        "component": {"name": name, "allowRemoteAccess": True, "position": {"x": 20, "y": 20}},
    })
    processor = request(f"/process-groups/{group}/processors", {
        "revision": {"version": 0},
        "component": {
            "name": f"Verify {name}", "type": "org.apache.nifi.processors.standard.InvokeHTTP",
            "bundle": {"group": "org.apache.nifi", "artifact": "nifi-standard-nar", "version": "2.12.0"},
            "position": {"x": 380, "y": 20},
            "config": {
                "properties": {
                    "HTTP Method": "POST", "HTTP URL": "http://c2-observer:8001/test-data",
                },
                "autoTerminatedRelationships": ["Original", "Response", "Retry", "No Retry", "Failure"],
            },
        },
    })
    request(f"/process-groups/{group}/connections", {
        "revision": {"version": 0},
        "component": {
            "source": {"id": port["id"], "type": "INPUT_PORT", "groupId": group},
            "destination": {"id": processor["id"], "type": "PROCESSOR", "groupId": group},
        },
    })
    for resource, entity in (("processors", processor), ("input-ports", port)):
        request(f"/{resource}/{entity['id']}/run-status", {
            "revision": entity["revision"], "state": "RUNNING",
        }, "PUT")
    return {"id": port["id"], "name": name}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin", default="http://127.0.0.1:8080")
    args = parser.parse_args()
    print(json.dumps(create_receiver(args.origin)))
