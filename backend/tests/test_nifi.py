"""Validate the actual MiNiFi to NiFi HTTP Site-to-Site data path."""

from hashlib import sha256
import os
import time
import unittest
from urllib.error import HTTPError
from uuid import uuid4

from nifi_fixture import create_receiver
from test_cpp import CPP_ID
from test_smoke import AGENT_ID, UI, get_json
from test_workflow import draft, post


@unittest.skipUnless(os.environ.get("OEM_SMOKE_NIFI"), "requires the NiFi Compose overlay")
class SiteToSiteTest(unittest.TestCase):
    def test_both_agents_deliver_flowfiles_to_the_selected_input_port(self):
        port = create_receiver()
        self.assertIn(port, get_json(f"{UI}/api/v1/nifi/input-ports"))

        agents = [("minifi-java", AGENT_ID)]
        if os.environ.get("OEM_SMOKE_CPP"):
            agents.append(("minifi-cpp", CPP_ID))

        for runtime, agent_id in agents:
            with self.subTest(runtime=runtime):
                payload = draft()
                data = f"Transferred through NiFi Site-to-Site from {runtime}: {uuid4()}"
                definition = payload["definition"]
                definition["runtime"] = runtime
                definition["nodes"][0]["config"] = {
                    "Data Format": "Text", "Unique FlowFiles": False, "Custom Text": data,
                }
                definition["nodes"][1] = {
                    "id": "nifi", "type": "RemoteProcessGroup", "target_port_id": port["id"],
                }
                definition["connections"][0]["target"] = "nifi"
                self.assertEqual(post("/flows", payload)["validation_errors"], [])
                path = f"/flows/{payload['id']}"
                saved = get_json(f"{UI}/api/v1{path}")["definition"]
                self.assertEqual(saved["nodes"][1]["target_port_id"], port["id"])
                self.assertEqual(saved["nodes"][0]["config"]["Custom Text"], data)
                post(f"{path}/publish", {})
                deployment = post("/deployments", {"flow_id": payload["id"], "agent_id": agent_id})

                expected = sha256(data.encode()).hexdigest()
                deadline = time.monotonic() + 65
                while time.monotonic() < deadline:
                    state = get_json(f"{UI}/api/v1/deployments/{deployment['id']}")
                    self.assertNotEqual(state["status"], "FAILED", state)
                    receipts = get_json("http://c2-observer:8001/test-data")
                    if state["status"] == "APPLIED" and any(item["sha256"] == expected for item in receipts):
                        self.assertEqual(state["ack_state"], "FULLY_APPLIED")
                        print(f"{runtime} delivered payload {expected} through NiFi Input Port {port['id']}")
                        break
                    time.sleep(1)
                else:
                    self.fail(f"{runtime}: NiFi did not forward the expected bytes. Deployment: {state}")

    def test_unknown_port_uuid_cannot_be_published(self):
        payload = draft()
        payload["definition"]["nodes"][1] = {
            "id": "nifi", "type": "RemoteProcessGroup", "target_port_id": str(uuid4()),
        }
        payload["definition"]["connections"][0]["target"] = "nifi"
        self.assertEqual(post("/flows", payload)["validation_errors"], [])
        with self.assertRaises(HTTPError) as error:
            post(f"/flows/{payload['id']}/publish", {})
        with error.exception as response:
            self.assertEqual(response.status, 422)
            self.assertIn(b"not advertised by the internal NiFi", response.read())
