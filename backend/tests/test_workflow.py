"""Deploy a compiled flow through the real Java agent's outbound C2 connection."""

import json
import os
import time
import unittest
from hashlib import sha256
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

from app.compiler import component_id
from app.catalog import CONTROLLER_SERVICES, PROCESSORS
from app.db import SessionLocal
from app.models import Agent, Flow, FlowArtifact, FlowRevision

from test_smoke import AGENT_ID, OBSERVER, UI, get_json


def post(path, payload, method="POST"):
    request = Request(
        f"{UI}/api/v1{path}", data=json.dumps(payload).encode(), method=method,
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
    def test_catalog_file_route_and_http_payload_on_real_agent(self):
        catalog = get_json(f"{UI}/api/v1/catalog")
        self.assertEqual({key for key, value in catalog.items() if "configuration" in value}, set(PROCESSORS))
        self.assertEqual(len(PROCESSORS), 117)
        editor = get_json(f"{UI}/api/v1/flow-editor")
        self.assertEqual(set(editor["controller_services"]), set(CONTROLLER_SERVICES))
        self.assertEqual(len(CONTROLLER_SERVICES), 47)
        expected_components = {
            (entry["type"], *(entry["bundle"][key] for key in ("group", "artifact", "version")))
            for catalog_entries in (PROCESSORS, CONTROLLER_SERVICES)
            for entry in catalog_entries.values()
        }
        with SessionLocal() as db:
            observed = {tuple(entry) for entry in db.get(Agent, AGENT_ID).capabilities["minifi_components"]}
        self.assertEqual(expected_components - observed, set())
        payload = draft()
        flow_id = payload["id"]
        name = f"{flow_id}.txt"
        data = f"real edge data {flow_id}".encode()
        input_directory = Path("/tmp/oem-smoke-input") / flow_id
        input_directory.mkdir()
        # The pinned image runs the agent as uid/gid 1000. GetFile requires a writable directory.
        os.chown(input_directory, 1000, 1000)
        (input_directory / name).write_bytes(data)
        definition = payload["definition"]
        definition["nodes"] = [
            {
                "id": "file", "type": "GetFile", "scheduling": {"period": "1 sec"},
                "config": {"Input Directory": str(input_directory), "File Filter": name,
                           "Keep Source File": True, "Polling Interval": "1 sec"},
            },
            {
                "id": "attribute", "type": "UpdateAttribute",
                "attributes": {"oem.milestone": "${filename}"},
            },
            {
                "id": "route", "type": "RouteOnAttribute",
                "attributes": {"example": "${oem.milestone:isEmpty():not()}"},
            },
            {
                "id": "http", "type": "InvokeHTTP",
                "config": {"HTTP Method": "POST", "HTTP URL": "http://c2-observer:8001/test-data"},
                "attributes": {"x-oem-test": "${oem.milestone}"},
            },
        ]
        definition["connections"] = [
            {"id": "file", "source": "file", "target": "attribute"},
            {"id": "enriched", "source": "attribute", "target": "route"},
            {"id": "example", "source": "route", "source_relationship": "example", "target": "http"},
        ]
        self.assertEqual(post("/flows", payload)["validation_errors"], [])
        base = f"/flows/{flow_id}"
        stored = get_json(f"{UI}/api/v1{base}")["definition"]
        self.assertEqual(stored["nodes"][1]["attributes"], definition["nodes"][1]["attributes"])
        self.assertEqual(stored["connections"][2]["source_relationship"], "example")
        with SessionLocal() as db:
            self.assertEqual(db.get(FlowRevision, (flow_id, 1)).definition, stored)
        self.assert_deployed(flow_id, 1, post(f"{base}/publish", {})["sha256"])
        expected = {"sha256": sha256(data).hexdigest(), "labels": name}
        for _ in range(25):
            if expected in get_json("http://c2-observer:8001/test-data"):
                print(f"MiNiFi sent file payload {expected['sha256']} to the real HTTP receiver")
                break
            time.sleep(1)
        else:
            self.fail("MiNiFi did not send the file and its dynamic header to the HTTP receiver")

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

    def test_saved_revisions_deploy_distinct_processor_configurations(self):
        payload = draft()
        flow_id = payload["id"]
        base = f"/flows/{flow_id}"
        definition = payload["definition"]
        generator, logger = definition["nodes"]
        generator.update({
            "label": "Emit saved sample", "description": "Literal test data", "position": {"x": 130, "y": 90},
            "config": {"Data Format": "Text", "Custom Text": "first sample", "Batch Size": 2, "Mime Type": "text/plain"},
            "attributes": {"sample.kind": "first"},
            "scheduling": {"period": "2 sec", "bulletin_level": "INFO"},
        })
        logger["config"] = {"Log Prefix": "OEM sample A", "Output Format": "Single Line", "Log Payload": True}
        definition["connections"][0]["queue"] = {"object_threshold": 16, "data_size_threshold": "128 KB", "expiration": "30 sec"}
        self.assertEqual(post("/flows", payload)["validation_errors"], [])
        first = post(f"{base}/publish?version=1", {})
        self.assert_deployed(flow_id, 1, first["sha256"])

        generator["config"].update({"Custom Text": "second sample", "Batch Size": 3})
        generator["attributes"]["sample.kind"] = "second"
        generator["scheduling"]["period"] = "3 sec"
        logger["config"]["Log Prefix"] = "OEM sample B"
        definition["connections"][0]["queue"]["object_threshold"] = 32
        edit = {"expected_version": 1, "name": payload["name"], "definition": definition}
        updated = post(base, edit, method="PUT")
        self.assertEqual(updated["version"], 2)
        self.assertEqual(updated["validation_errors"], [])
        with self.assertRaises(HTTPError) as conflict:
            post(base, edit, method="PUT")
        with conflict.exception as response:
            self.assertEqual(response.status, 409)
        self.assertEqual(get_json(f"{UI}/api/v1{base}/versions/1")["definition"]["nodes"][0]["config"]["Custom Text"],
                         "first sample")
        stored = get_json(f"{UI}/api/v1{base}")["definition"]
        self.assertEqual(stored["nodes"][0]["position"], {"x": 130, "y": 90})
        self.assertEqual(stored["nodes"][0]["config"], generator["config"])
        self.assertEqual(stored["nodes"][0]["attributes"], generator["attributes"])
        self.assertEqual(stored["nodes"][0]["scheduling"], generator["scheduling"])
        self.assertEqual(stored["connections"][0]["queue"], definition["connections"][0]["queue"])
        with SessionLocal() as db:
            self.assertEqual(db.get(FlowRevision, (flow_id, 2)).definition, stored)
        second = post(f"{base}/publish?version=2", {})
        self.assertNotEqual(first["sha256"], second["sha256"])
        self.assert_deployed(flow_id, 2, second["sha256"])
        self.assert_deployed(flow_id, 1, first["sha256"])

    def assert_deployed(self, flow_id, version, digest):
        queued = post("/deployments", {"flow_id": flow_id, "version": version, "agent_id": AGENT_ID})
        for _ in range(60):
            deployment = get_json(f"{UI}/api/v1/deployments/{queued['id']}")
            self.assertNotEqual(deployment["status"], "FAILED", deployment)
            if deployment["status"] == "APPLIED":
                self.assertEqual(deployment["ack_state"], "FULLY_APPLIED")
                self.assertEqual(deployment["sha256"], digest)
                self.assertIn(
                    {"kind": "configuration", "operation_id": queued["id"], "sha256": digest},
                    get_json(OBSERVER),
                )
                self.assertTrue(any(row["id"] == queued["id"] for row in get_json(
                    f"{UI}/api/v1/deployments?agent_id={AGENT_ID}&flow_id={flow_id}&status=APPLIED",
                )))
                return
            time.sleep(1)
        self.fail(f"Flow revision did not reach APPLIED: {deployment}")

    def test_controller_services_transform_data_on_real_agent(self):
        payload = draft()
        flow_id = payload["id"]
        definition = payload["definition"]
        body = json.dumps({"check": flow_id}, separators=(",", ":"))
        definition["nodes"] = [
            {"id": "generate", "type": "GenerateFlowFile", "config": {"Data Format": "Text", "Custom Text": body}},
            {"id": "convert", "type": "ConvertRecord",
             "config": {"Record Reader": "reader", "Record Writer": "writer"}},
            {"id": "http", "type": "InvokeHTTP",
             "config": {"HTTP Method": "POST", "HTTP URL": "http://c2-observer:8001/test-data"},
             "attributes": {"x-oem-test": flow_id}},
        ]
        definition["controller_services"] = [
            {"id": "reader", "type": "JsonTreeReader", "label": "JSON reader"},
            {"id": "writer", "type": "JsonRecordSetWriter", "config": {"Output Grouping": "output-array"}},
        ]
        definition["connections"] = [
            {"id": "input", "source": "generate", "target": "convert"},
            {"id": "output", "source": "convert", "target": "http"},
        ]
        self.assertEqual(post("/flows", payload)["validation_errors"], [])
        stored = get_json(f"{UI}/api/v1/flows/{flow_id}")["definition"]
        with SessionLocal() as db:
            self.assertEqual(db.get(FlowRevision, (flow_id, 1)).definition, stored)
        artifact = post(f"/flows/{flow_id}/publish", {})
        self.assert_deployed(flow_id, 1, artifact["sha256"])
        expected = {"sha256": sha256(f"[{body}]".encode()).hexdigest(), "labels": flow_id}
        for _ in range(25):
            if expected in get_json("http://c2-observer:8001/test-data"):
                print(f"MiNiFi sent the converted JSON array {expected['sha256']} to the real HTTP receiver")
                break
            time.sleep(1)
        else:
            self.fail("The receiver did not get the JSON array produced by ConvertRecord")

    def test_execution_processors_require_a_separate_deployment_opt_in(self):
        payload = draft("ExecuteProcess")
        flow_id = payload["id"]
        payload["definition"]["nodes"][0]["config"] = {"Command": "/bin/true"}
        self.assertEqual(post("/flows", payload)["validation_errors"], [])
        post(f"/flows/{flow_id}/publish", {})
        with self.assertRaises(HTTPError) as error:
            post("/deployments", {"flow_id": flow_id, "agent_id": AGENT_ID})
        with error.exception as response:
            self.assertEqual(response.status, 403)

    def test_invalid_processor_configuration_is_preserved_in_unpublishable_draft(self):
        payload = draft()
        payload["definition"]["nodes"][0]["config"] = {
            "File Size": "400 MB", "Custom Text": "${literal}",
            "Batch Size": [], "Nonexistent": "test",
        }
        result = post("/flows", payload)
        for name in payload["definition"]["nodes"][0]["config"]:
            self.assertTrue(any(name in error for error in result["validation_errors"]))
        with self.assertRaises(HTTPError) as error:
            post(f"/flows/{payload['id']}/publish", {})
        with error.exception as response:
            self.assertEqual(response.status, 422)

    def test_sensitive_descriptors_are_visible_but_values_are_not_persisted(self):
        catalog = get_json(f"{UI}/api/v1/catalog")
        self.assertTrue(catalog["InvokeHTTP"]["configuration"]["properties"]["Request Password"]["sensitive"])
        payload = draft("InvokeHTTP")
        payload["definition"]["nodes"][0]["config"] = {"Request Password": "dummy-test-value"}
        with self.assertRaises(HTTPError) as error:
            post("/flows", payload)
        with error.exception as response:
            self.assertEqual(response.status, 422)
            self.assertNotIn(b"dummy-test-value", response.read())
        with SessionLocal() as db:
            self.assertIsNone(db.get(Flow, payload["id"]))

    def test_unsupported_draft_cannot_be_published_or_deployed(self):
        payload = draft(processor="ConsumeKafka")
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
