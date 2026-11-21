"""Exercise the pinned native agent over the same outbound C2 routes as Java."""

import os
import time
import unittest
from urllib.error import HTTPError

from app.compiler import component_id
from app.db import SessionLocal
from app.models import FlowArtifact, FlowRevision
from test_smoke import AGENT_ID, OBSERVER, UI, get_json
from test_workflow import draft, post

CPP_ID = "oem-test-agent-cpp"


@unittest.skipUnless(os.environ.get("OEM_SMOKE_CPP"), "requires the native Compose overlay")
class CppDeploymentTest(unittest.TestCase):
    def test_native_manifest_and_two_published_revisions(self):
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            agents = get_json(f"{UI}/api/v1/agents?deployable=true")
            by_id = {agent["id"]: agent for agent in agents}
            if CPP_ID in by_id and AGENT_ID in by_id:
                break
            time.sleep(1)
        else:
            self.fail(f"Both real agents must report usable manifests: {agents}")
        self.assertEqual(by_id[CPP_ID]["runtime"], "minifi-cpp")
        self.assertEqual(by_id[CPP_ID]["runtime_version"], "1.1.0")
        self.assertEqual(by_id[AGENT_ID]["runtime"], "minifi-java")
        self.assertEqual(
            set(get_json(f"{UI}/api/v1/catalog?runtime=minifi-cpp")),
            {"GenerateFlowFile", "UpdateAttribute", "LogAttribute"},
        )
        self.assertIn("ConvertRecord", get_json(f"{UI}/api/v1/catalog"))
        payload = draft()
        flow_id = payload["id"]
        definition = payload["definition"]
        definition["runtime"] = "minifi-cpp"
        definition["nodes"][0]["config"] = {"Data Format": "Text", "Unique FlowFiles": False, "Custom Text": "native one"}
        definition["nodes"][1]["config"] = {"Log Payload": True}
        base = f"/flows/{flow_id}"
        first = post("/flows", payload)
        self.assertEqual(first["validation_errors"], [])
        published = post(f"{base}/publish", {})
        self.assertEqual((published["runtime"], published["runtime_version"]), ("minifi-cpp", "1.1.0"))
        with self.assertRaises(HTTPError) as rejected:
            post("/deployments", {"flow_id": flow_id, "agent_id": AGENT_ID})
        with rejected.exception as response:
            self.assertEqual(response.status, 409)
        self.assert_applied(flow_id, published)

        definition["nodes"][0]["config"]["Custom Text"] = "native two"
        definition["nodes"].append({"id": "update", "type": "UpdateAttribute", "attributes": {"oem.test": "second"}})
        definition["connections"][0]["target"] = "update"
        definition["connections"].append({"id": "updated", "source": "update", "target": "log"})
        edit = {"expected_version": 1, "name": payload["name"], "definition": definition}
        self.assertEqual(post(base, edit, "PUT")["validation_errors"], [])
        published_two = post(f"{base}/publish", {})
        self.assertNotEqual(published["sha256"], published_two["sha256"])
        self.assert_applied(flow_id, published_two)
        stored = get_json(f"{UI}/api/v1{base}")["definition"]
        with SessionLocal() as db:
            self.assertEqual(db.get(FlowRevision, (flow_id, 2)).definition, stored)
            self.assertEqual(db.get(FlowArtifact, (flow_id, 2)).runtime, "minifi-cpp")
        self.assertEqual(stored["nodes"][2]["attributes"], {"oem.test": "second"})

    def assert_applied(self, flow_id, published):
        queued = post("/deployments", {"flow_id": flow_id, "version": published["version"], "agent_id": CPP_ID})
        operation_id = queued["id"]
        digest = published["sha256"]
        logger = component_id(flow_id, "processor", "log")
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            state = get_json(f"{UI}/api/v1/deployments/{operation_id}")
            self.assertNotEqual(state["status"], "FAILED", state)
            observations = get_json(OBSERVER)
            if state["status"] == "APPLIED" and any(
                event["kind"] == "heartbeat" and event["identity"]["id"] == CPP_ID and event["flow"]["flowId"] == digest
                and any(item["id"] == logger and item["flowFilesIn"] > 0 for item in event["flow"]["processorStatuses"])
                for event in observations
            ):
                self.assertEqual(state["ack_state"], "FULLY_APPLIED")
                self.assertIn({"kind": "configuration", "operation_id": operation_id, "sha256": digest}, observations)
                self.assertTrue(any(command["identifier"] == operation_id
                    and command["args"]["location"] == f"configuration/{operation_id}"
                    for event in observations if event["kind"] == "heartbeat" and event["identity"]["id"] == CPP_ID
                    for command in event["operations"]))
                print(f"Native MiNiFi ran revision {published['version']} ({digest})")
                return
            time.sleep(1)
        self.fail(f"Native revision did not reach APPLIED with processed FlowFiles: {state}")
