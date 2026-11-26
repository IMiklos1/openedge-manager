"""Integration tests for a fresh Compose project with the C2 probe enabled."""

import json
import os
import socket
import time
import unittest
from datetime import datetime
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

import boto3
from botocore import UNSIGNED
from botocore.config import Config
from botocore.exceptions import ClientError
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Agent, C2Probe

API = "http://api:8000"
UI = "http://ui:5173"
AGENT_ID = "oem-smoke-agent-01"
OBSERVER = "http://c2-observer:8001/observations"
AGENTS = "/api/v1/agents"
C2 = f"{API}/c2-protocol"


def get_json(url):
    with urlopen(url, timeout=5) as response:
        return json.load(response)


def post_c2(path, payload):
    request = Request(
        f"{C2}/{path}", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urlopen(request, timeout=5) as response:
        return response.status, response.read()


def read_probe():
    with SessionLocal() as db:
        return db.scalar(select(C2Probe).where(C2Probe.agent_id == AGENT_ID))


class ComposeSmokeTest(unittest.TestCase):
    def test_api_and_ui_proxy(self):
        self.assertEqual(get_json(f"{API}/health")["status"], "ok")
        with urlopen(UI, timeout=5) as response:
            self.assertIn(b"OpenEdge Manager", response.read())
        self.assertEqual(get_json(f"{UI}/api/v1/catalog"), get_json(f"{API}/api/v1/catalog"))
        self.assertIn("/api/v1/agents", get_json(f"{UI}/openapi.json")["paths"])

    def test_invalid_heartbeat_and_unknown_ack(self):
        with self.assertRaises(HTTPError) as error:
            post_c2("heartbeat", {"agentInfo": {}})
        with error.exception as response:
            self.assertEqual(response.code, 422)

        with self.assertRaises(HTTPError) as error:
            post_c2("acknowledge", {
                "operationId": str(uuid4()),
                "operationState": {"state": "FULLY_APPLIED"},
            })
        with error.exception as response:
            self.assertEqual(response.code, 404)

    def test_cpp_windows_hostname_legacy_bytes_are_scoped_to_the_hostname(self):
        agent_id = str(uuid4())
        hostname = "Tesztszámító"
        payload = {
            "agentInfo": {"identifier": agent_id, "agentManifest": {
                "agentType": "cpp", "buildInfo": {"version": "1.1.0"},
                "bundles": [{
                    "group": "org.apache.nifi.minifi", "artifact": "minifi-standard-processors", "version": "1.1.0",
                    "componentManifest": {"processors": [{"type": "org.apache.nifi.minifi.processors.GetFile"}]},
                }],
            }},
            "deviceInfo": {"systemInfo": {"operatingSystem": "Windows", "machineArch": "x86_64"},
                           "networkInfo": {"hostname": hostname}},
        }
        message = json.dumps(payload, ensure_ascii=False).encode("cp1252")

        def send(body, operation="heartbeat"):
            return urlopen(Request(f"{C2}/{operation}", data=body,
                                   headers={"Content-Type": "application/json"}), timeout=5)

        with send(message) as response:
            self.assertEqual(response.status, 200)
        with SessionLocal() as db:
            agent = db.get(Agent, agent_id)
            self.assertEqual((agent.hostname, agent.os_name, agent.architecture), (hostname, "Windows", "x86_64"))
            self.assertEqual((agent.runtime, agent.runtime_version, agent.status), ("minifi-cpp", "1.1.0", "ONLINE"))
            self.assertEqual(agent.capabilities["minifi_components"][0][0], "org.apache.nifi.minifi.processors.GetFile")
        self.assertEqual(get_json(f"{API}{AGENTS}?q={agent_id}")[0]["hostname"], hostname)

        payload["deviceInfo"]["networkInfo"]["hostname"] = "Árvíztűrő tükörfúrógép"
        with send(json.dumps(payload, ensure_ascii=False).encode("utf-8")) as response:
            self.assertEqual(response.status, 200)
        self.assertEqual(get_json(f"{API}{AGENTS}?q={agent_id}")[0]["hostname"], "Árvíztűrő tükörfúrógép")

        invalid_messages = {
            "wrong runtime": message.replace(b'"cpp"', b'"minifi-java"'),
            "wrong OS": message.replace(b'"Windows"', b'"Linux"'),
            "invalid identifier": message.replace(agent_id.encode(), b'invalid-\xe1'),
            "invalid ignored field": message.replace(b'"networkInfo"', b'"ignored": "\xe1", "networkInfo"'),
            "duplicate key": message.replace(b'"hostname"', b'"hostname": "ambiguous", "hostname"'),
            "malformed JSON": message[:-1],
        }
        for case, body in invalid_messages.items():
            with self.subTest(case=case), self.assertRaises(HTTPError) as error:
                send(body)
            with error.exception as response:
                self.assertEqual(response.status, 422)
        with self.assertRaises(HTTPError) as error:
            send(b'{"operationId":"invalid-\xe1","operationState":{"state":"NO_OPERATION"}}', "acknowledge")
        with error.exception as response:
            self.assertEqual(response.status, 422)

    def test_c2_media_type_and_size_limit(self):
        cases = (
            (b"{}", "text/plain", 415),
            (b"x" * (4 * 1024 * 1024 + 1), "application/json", 413),
        )
        for body, media_type, status in cases:
            with self.subTest(status=status), self.assertRaises(HTTPError) as error:
                request = Request(
                    f"{C2}/heartbeat", data=body,
                    headers={"Content-Type": media_type},
                )
                urlopen(request, timeout=5)
            with error.exception as response:
                self.assertEqual(response.code, status)

    def test_redis(self):
        with socket.create_connection(("redis", 6379), timeout=5) as connection:
            connection.sendall(b"*1\r\n$4\r\nPING\r\n")
            with connection.makefile("rb") as response:
                self.assertEqual(response.readline(), b"+PONG\r\n")

    def test_s3_signed_round_trip(self):
        options = {"endpoint_url": "http://storage:8333", "region_name": "us-east-1"}
        bucket = os.environ["S3_BUCKET"]
        anonymous = boto3.client("s3", **options, config=Config(signature_version=UNSIGNED))
        with self.assertRaises(ClientError) as error:
            anonymous.head_bucket(Bucket=bucket)
        self.assertEqual(error.exception.response["ResponseMetadata"]["HTTPStatusCode"], 403)

        client = boto3.client("s3", **options, config=Config(
            signature_version="s3v4",
            connect_timeout=5,
            read_timeout=5,
            retries={"total_max_attempts": 1},
        ))
        key = f"smoke/{uuid4()}"
        body = b"OpenEdge S3 smoke test"
        client.put_object(Bucket=bucket, Key=key, Body=body)
        try:
            result = client.get_object(Bucket=bucket, Key=key)
            with result["Body"] as stored:
                self.assertEqual(stored.read(), body)
        finally:
            client.delete_object(Bucket=bucket, Key=key)


class RealAgentC2Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        deadline = time.monotonic() + 60
        observations = []
        while time.monotonic() < deadline:
            observations = get_json(OBSERVER)
            for index, event in enumerate(observations):
                if event["kind"] != "acknowledgement" or event["agent_id"] != AGENT_ID:
                    continue
                # The next heartbeat also proves the backend stopped offering the operation.
                followup = next((entry for entry in observations[index + 1:] if entry["kind"] == "heartbeat" and entry["identity"]["id"] == AGENT_ID), None)
                if followup is not None:
                    cls.delivery = next((entry for entry in observations[:index]
                                         if entry["kind"] == "heartbeat"
                                         and any(operation["identifier"] == event["operation_id"]
                                                 for operation in entry["operations"])), None)
                    cls.ack = event
                    cls.followup = followup
                    return
            time.sleep(1)
        kinds = [event["kind"] for event in observations]
        raise AssertionError(f"Expected a live agent heartbeat, ACK, and another heartbeat. Observed {kinds}")

    def test_heartbeat_persists_observed_inventory(self):
        identity = self.followup["identity"]
        self.assertEqual(identity["id"], AGENT_ID)
        self.assertEqual(identity["agent_class"], "openedge-test")
        self.assertEqual(identity["runtime"], "minifi-java")
        self.assertEqual(identity["runtime_version"], "2.12.0")
        self.assertEqual(identity["os_name"], "Linux")
        self.assertTrue(identity["architecture"])
        self.assertTrue(identity["hostname"])

        agents = get_json(f"{API}{AGENTS}")
        agent = next(row for row in agents if row["id"] == AGENT_ID)
        self.assertEqual({key: agent[key] for key in identity}, identity)
        self.assertEqual(agent["status"], "ONLINE")
        self.assertTrue(agent["can_deploy_flow"])
        self.assertIsNone(agent["deployment_blocker"])
        deployable = get_json(f"{API}{AGENTS}?deployable=true&q={AGENT_ID}")
        self.assertEqual([row["id"] for row in deployable], [AGENT_ID])
        filtered = get_json(f"{API}{AGENTS}?agent_class=openedge-test&q={AGENT_ID}&limit=1")
        self.assertEqual([row["id"] for row in filtered], [AGENT_ID])
        self.assertEqual(filtered[0]["health"], "RECENT")
        self.assertTrue(any(
            group["name"] == "openedge-test" and group["recent"] >= 1
            for group in get_json(f"{API}/api/v1/agent-classes")
        ))
        last_seen = datetime.fromisoformat(agent["last_seen"])

        with SessionLocal() as db:
            row = db.get(Agent, AGENT_ID)
            self.assertEqual({key: getattr(row, key) for key in identity}, identity)
            self.assertEqual(row.status, "ONLINE")
            self.assertGreaterEqual(row.last_seen, last_seen)
            self.assertGreater(row.last_seen, row.created_at)

    def test_ack_matches_the_command_sent_to_the_agent(self):
        delivery = self.delivery
        self.assertIsNotNone(delivery, "The agent ACK had no preceding heartbeat response")
        self.assertEqual(delivery["identity"]["id"], AGENT_ID)
        operation, = delivery["operations"]
        self.assertEqual(operation["operation"], "DESCRIBE")
        self.assertEqual(operation["operand"], "MANIFEST")
        self.assertEqual(self.ack["agent_id"], AGENT_ID)
        self.assertEqual(self.ack["operation_id"], operation["identifier"])
        self.assertEqual(self.ack["state"], "FULLY_APPLIED")
        self.assertEqual(self.followup["operations"], [])

        probe = read_probe()
        self.assertEqual(probe.operation_id, operation["identifier"])
        self.assertEqual(probe.ack_state, self.ack["state"])
        self.assertIsNotNone(probe.acknowledged_at)
        print(f"Observed Java {AGENT_ID} acknowledge DESCRIBE MANIFEST {probe.operation_id} as {probe.ack_state}")

        replay = {
            "operationId": probe.operation_id,
            "operationState": {"state": probe.ack_state},
            "agentInfo": {"identifier": AGENT_ID},
        }
        self.assertEqual(post_c2("acknowledge", replay), (204, b""))
        self.assertEqual(read_probe().acknowledged_at, probe.acknowledged_at)

        replay["operationState"]["state"] = "NOT_APPLIED"
        with self.assertRaises(HTTPError) as error:
            post_c2("acknowledge", replay)
        with error.exception as response:
            self.assertEqual(response.code, 409)
        self.assertEqual(read_probe().ack_state, "FULLY_APPLIED")

    def test_ack_with_another_reported_agent_is_rejected(self):
        probe = read_probe()
        with self.assertRaises(HTTPError) as error:
            post_c2("acknowledge", {
                "operationId": self.ack["operation_id"],
                "operationState": {"state": "FULLY_APPLIED"},
                "agentInfo": {"identifier": "another-agent"},
            })
        with error.exception as response:
            self.assertEqual(response.code, 404)
        self.assertEqual(read_probe().acknowledged_at, probe.acknowledged_at)
