"""Exercise the pinned native agent over the same outbound C2 routes as Java."""

from hashlib import sha256
import json
import os
import time
import unittest
from urllib.error import HTTPError

from app.compiler import component_id
from app.cpp_processors import CPP_PROCESSORS, CPP_SERVICES
from app.db import SessionLocal
from app.models import Agent, FlowArtifact, FlowRevision
from test_smoke import AGENT_ID, OBSERVER, UI, get_json
from test_workflow import draft, post

CPP_ID = "oem-test-agent-cpp"


@unittest.skipUnless(os.environ.get("OEM_SMOKE_CPP"), "requires the native Compose overlay")
class CppDeploymentTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            agents = get_json(f"{UI}/api/v1/agents?deployable=true")
            by_id = {agent["id"]: agent for agent in agents}
            if CPP_ID in by_id and AGENT_ID in by_id:
                break
            time.sleep(1)
        else:
            raise AssertionError(f"Both real agents must report usable manifests: {agents}")
        cls.agents = by_id

    def test_native_manifest_and_two_published_revisions(self):
        by_id = self.agents
        self.assertEqual(by_id[CPP_ID]["runtime"], "minifi-cpp")
        self.assertEqual(by_id[CPP_ID]["runtime_version"], "1.1.0")
        self.assertEqual(by_id[AGENT_ID]["runtime"], "minifi-java")
        catalog = get_json(f"{UI}/api/v1/catalog?runtime=minifi-cpp")
        services = get_json(f"{UI}/api/v1/flow-editor?runtime=minifi-cpp")["controller_services"]
        self.assertEqual(set(catalog), set(CPP_PROCESSORS))
        self.assertEqual(set(services), set(CPP_SERVICES))
        self.assertEqual((len(catalog), len(services)), (94, 22))
        expected = {
            (item["type"], *(item["bundle"][key] for key in ("group", "artifact", "version")))
            for item in (*CPP_PROCESSORS.values(), *CPP_SERVICES.values()) if "Linux" in item["platforms"]
        }
        with SessionLocal() as db:
            components = {tuple(item) for item in db.get(Agent, CPP_ID).capabilities["minifi_components"]}
        self.assertEqual(components, expected)
        self.assertEqual(catalog["FetchSmb"]["configuration"]["platforms"], ["Windows"])
        self.assertTrue(catalog["InvokeHTTP"]["configuration"]["properties"]["invokehttp-proxy-password"]["sensitive"])
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

    def test_native_records_dynamic_route_and_http_payload(self):
        payload = draft()
        flow_id = payload["id"]
        definition = payload["definition"]
        definition.update(
            runtime="minifi-cpp",
            controller_services=[
                {"id": "reader", "type": "JsonTreeReader"},
                {"id": "writer", "type": "JsonRecordSetWriter", "config": {"Output Grouping": "Array"}},
            ],
            nodes=[
                self.generator('{ "sample": 23 }'),
                {"id": "convert", "type": "ConvertRecord", "config": {"Record Reader": "reader", "Record Writer": "writer"}},
                {"id": "tag", "type": "UpdateAttribute", "attributes": {"x-oem-test": flow_id}},
                {"id": "route", "type": "RouteOnAttribute", "attributes": {"send": "${'x-oem-test':isEmpty():not()}"}},
                self.http_receiver(),
            ],
            connections=[
                {"id": "raw", "source": "generate", "target": "convert"},
                {"id": "records", "source": "convert", "target": "tag"},
                {"id": "tagged", "source": "tag", "target": "route"},
                {"id": "selected", "source": "route", "source_relationship": "send", "target": "http"},
            ],
        )
        self.assertEqual(post("/flows", payload)["validation_errors"], [])
        published = post(f"/flows/{flow_id}/publish", {})
        saved = get_json(f"{UI}/api/v1/flows/{flow_id}")["definition"]
        with SessionLocal() as db:
            self.assertEqual(db.get(FlowRevision, (flow_id, 1)).definition, saved)
            artifact = json.loads(db.get(FlowArtifact, (flow_id, 1)).content)["rootGroup"]
        self.assertEqual(artifact["processors"][1]["properties"]["Record Reader"], artifact["controllerServices"][0]["identifier"])
        self.assert_applied(flow_id, published, "http")
        self.assert_received(flow_id, b'[{"sample":23}]')

    def test_native_python_execution_requires_opt_in(self):
        payload = draft()
        flow_id = payload["id"]
        script = (
            "def onTrigger(context, session):\n"
            "    flow_file = session.get()\n"
            "    if flow_file is None:\n"
            "        return\n"
            f"    flow_file.addAttribute('x-oem-test', '{flow_id}')\n"
            "    session.transfer(flow_file, REL_SUCCESS)\n"
        )
        payload["definition"].update(
            runtime="minifi-cpp",
            nodes=[self.generator("C++ Python"),
                   {"id": "script", "type": "ExecuteScript", "config": {"Script Engine": "python", "Script Body": script}},
                   self.http_receiver()],
            connections=[{"id": "in", "source": "generate", "target": "script"},
                         {"id": "out", "source": "script", "target": "http"}],
        )
        self.assertEqual(post("/flows", payload)["validation_errors"], [])
        published = post(f"/flows/{flow_id}/publish", {})
        if os.environ.get("MINIFI_ALLOW_EXECUTION_PROCESSORS", "").lower() == "true":
            self.assert_applied(flow_id, published, "http")
            self.assert_received(flow_id, b"C++ Python")
        else:
            with self.assertRaises(HTTPError) as rejected:
                post("/deployments", {"flow_id": flow_id, "agent_id": CPP_ID})
            with rejected.exception as response:
                self.assertEqual(response.status, 403)

    def test_native_manifest_rejects_other_platform(self):
        payload = draft()
        payload["definition"].update(
            runtime="minifi-cpp",
            nodes=[{"id": "event-log", "type": "TailEventLog", "config": {}}],
            connections=[],
        )
        self.assertEqual(post("/flows", payload)["validation_errors"], [])
        post(f"/flows/{payload['id']}/publish", {})
        with self.assertRaises(HTTPError) as rejected:
            post("/deployments", {"flow_id": payload["id"], "agent_id": CPP_ID})
        with rejected.exception as response:
            self.assertEqual(response.status, 409)
            self.assertIn("TailEventLog", json.load(response)["detail"])

    def test_native_platform_fields_and_sensitive_values(self):
        payload = draft()
        definition = payload["definition"]
        definition.update(runtime="minifi-cpp", controller_services=[{
            "id": "tls", "type": "SSLContextService", "config": {"Certificate Store Location": "CurrentUser"},
        }])
        self.assertEqual(post("/flows", payload)["validation_errors"], [])
        post(f"/flows/{payload['id']}/publish", {})
        with self.assertRaises(HTTPError) as rejected:
            post("/deployments", {"flow_id": payload["id"], "agent_id": CPP_ID})
        with rejected.exception as response:
            self.assertEqual(response.status, 409)
            self.assertIn("Certificate Store Location requires Windows", json.load(response)["detail"])

        definition["controller_services"][0]["config"]["Passphrase"] = "invalid-test-value"
        with self.assertRaises(HTTPError) as rejected:
            post(f"/flows/{payload['id']}", {"expected_version": 1, **payload}, "PUT")
        with rejected.exception as response:
            self.assertEqual(response.status, 422)
        with SessionLocal() as db:
            self.assertIsNone(db.get(FlowRevision, (payload["id"], 2)))

    @staticmethod
    def generator(body):
        return {"id": "generate", "type": "GenerateFlowFile", "config": {
            "Data Format": "Text", "Unique FlowFiles": False, "Custom Text": body,
        }}

    @staticmethod
    def http_receiver():
        return {"id": "http", "type": "InvokeHTTP", "config": {
            "HTTP Method": "POST", "Remote URL": "http://c2-observer:8001/test-data", "Attributes to Send": "x-oem-test",
        }}

    def assert_received(self, label, body):
        expected = {"sha256": sha256(body).hexdigest(), "labels": label}
        for _ in range(20):
            if expected in get_json("http://c2-observer:8001/test-data"):
                return
            time.sleep(1)
        self.fail(f"Native agent did not send the expected payload and header: {expected}")

    def assert_applied(self, flow_id, published, observed_node="log"):
        queued = post("/deployments", {"flow_id": flow_id, "version": published["version"], "agent_id": CPP_ID})
        operation_id = queued["id"]
        digest = published["sha256"]
        observed_processor = component_id(flow_id, "processor", observed_node)
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            state = get_json(f"{UI}/api/v1/deployments/{operation_id}")
            self.assertNotEqual(state["status"], "FAILED", state)
            observations = get_json(OBSERVER)
            if state["status"] == "APPLIED" and any(
                event["kind"] == "heartbeat" and event["identity"]["id"] == CPP_ID and event["flow"]["flowId"] == digest
                and any(item["id"] == observed_processor and item["flowFilesIn"] > 0 for item in event["flow"]["processorStatuses"])
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
