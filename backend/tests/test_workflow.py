"""Deploy a compiled flow through the real Java agent's outbound C2 connection."""

import json
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

from app.compiler import component_id
from app.db import SessionLocal
from app.models import FlowArtifact

from test_smoke import AGENT_ID, OBSERVER, UI, get_json


def post(path, payload):
    request = Request(
        f"{UI}/api/v1{path}", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urlopen(request, timeout=5) as response:
        return json.load(response)


def draft(processor="GenerateFlowFile"):
    flow_id = str(uuid4())
    name = "MiNiFi integration test"
    return {
        "id": flow_id, "name": name,
        "definition": {
            "schema_version": "1.0", "flow_id": flow_id, "name": name,
            "nodes": [{"id": "generate", "type": processor}, {"id": "log", "type": "LogAttribute"}],
            "connections": [{"id": "generated-file", "source": "generate", "target": "log"}],
        },
    }


class WorkflowTest(unittest.TestCase):
    def test_real_agent_downloads_applies_and_runs_flow(self):
        payload = draft()
        flow_id = payload["id"]
        self.assertEqual(post("/flows", payload)["validation_errors"], [])

        path = f"/flows/{flow_id}/publish"
        published = post(path, {})
        self.assertEqual(published, post(path, {}))
        self.assertEqual(published["runtime_version"], "2.12.0")
        artifact_hash = published["sha256"]
        with SessionLocal() as db:
            self.assertEqual(db.get(FlowArtifact, (flow_id, 1)).sha256, artifact_hash)

        with self.assertRaises(HTTPError) as error:
            post("/deployments", {"flow_id": flow_id, "agent_id": "different-agent"})
        with error.exception as response:
            self.assertEqual(response.status, 403)

        queued = post("/deployments", {"flow_id": flow_id, "agent_id": AGENT_ID})
        self.assertEqual(queued["status"], "PENDING")
        operation_id = queued["id"]
        now = time.monotonic()
        logger_id = component_id(flow_id, "processor", "log")
        while time.monotonic() < now + 90:
            deployment = get_json(f"{UI}/api/v1/deployments/{operation_id}")
            self.assertNotEqual(deployment["status"], "FAILED", deployment)
            observations = get_json(OBSERVER)
            log_processed = any(
                event["kind"] == "heartbeat"
                and event["flow"].get("flowId") == artifact_hash
                and any(
                    processor["id"] == logger_id and processor.get("flowFilesIn", 0) > 0
                    for processor in event["flow"].get("processorStatuses", [])
                )
                for event in observations
            )
            if deployment["status"] == "APPLIED" and log_processed:
                break
            time.sleep(1)
        else:
            self.fail(f"Deployment failed to reach APPLIED with processed FlowFiles: {deployment}")

        self.assertTrue(any(
            command == {
                "identifier": operation_id, "operation": "UPDATE", "operand": "CONFIGURATION",
                "args": {"flowId": artifact_hash, "relativeFlowUrl": f"configuration/{operation_id}"},
            }
            for event in observations if event["kind"] == "heartbeat" for command in event["operations"]
        ))
        self.assertIn({"kind": "configuration", "operation_id": operation_id, "sha256": artifact_hash}, observations)
        self.assertTrue(any(
            event["kind"] == "acknowledgement" and event["operation_id"] == operation_id
            and event["state"] == "FULLY_APPLIED" for event in observations
        ))
        self.assertEqual(deployment["ack_state"], "FULLY_APPLIED")
        self.assertIsNotNone(deployment["applied_at"])
        print(f"MiNiFi applied {artifact_hash} and LogAttribute received a FlowFile (deployment {operation_id})")

        # A new delivery of the same immutable artifact is a no-op on the Java agent.
        repeated = post("/deployments", {"flow_id": flow_id, "agent_id": AGENT_ID})
        retry_id = repeated["id"]
        until = time.monotonic() + 35
        while time.monotonic() < until:
            state = get_json(f"{UI}/api/v1/deployments/{retry_id}")
            self.assertNotEqual(state["status"], "FAILED", state)
            if state["status"] == "APPLIED":
                break
            time.sleep(1)
        else:
            self.fail(f"Repeat deployment did not confirm the running flow: {state}")
        self.assertEqual(state["ack_state"], "NO_OPERATION")
        self.assertFalse(any(
            event["kind"] == "configuration" and event["operation_id"] == retry_id
            for event in get_json(OBSERVER)
        ))

    def test_unsupported_draft_cannot_be_published_or_deployed(self):
        payload = draft(processor="GetFile")
        flow_id = payload["id"]
        post("/flows", payload)
        for path, body, expected in (
            (f"/flows/{flow_id}/publish", {}, 422),
            ("/deployments", {"flow_id": flow_id, "agent_id": AGENT_ID}, 409),
        ):
            with self.subTest(path=path), self.assertRaises(HTTPError) as error:
                post(path, body)
            with error.exception as response:
                self.assertEqual(response.status, expected)
        self.assertEqual(get_json(f"{UI}/api/v1/flows/{flow_id}")["status"], "DRAFT")
