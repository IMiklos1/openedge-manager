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
from app.models import C2Probe

API = "http://api:8000"
UI = "http://ui:5173"
AGENT_ID = "oem-test-agent-01"
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

    def test_real_agent_heartbeat_and_ack(self):
        deadline = time.monotonic() + 60
        first_seen = None
        agent = probe = None
        while time.monotonic() < deadline:
            agents = get_json(f"{API}{AGENTS}")
            agent = next((row for row in agents if row["id"] == AGENT_ID), None)
            probe = read_probe()
            if agent:
                last_seen = datetime.fromisoformat(agent["last_seen"])
                if first_seen is None:
                    first_seen = last_seen
                if last_seen > first_seen and probe and probe.acknowledged_at:
                    break
            time.sleep(1)
        else:
            self.fail(f"Timed out waiting for repeated agent heartbeats and a stored ACK. Agent={bool(agent)}, probe={bool(probe)}")

        self.assertEqual(agent["agent_class"], "openedge-test")
        self.assertEqual(agent["runtime"], "minifi-cpp")
        self.assertEqual(agent["runtime_version"], "1.1.0")
        self.assertEqual(agent["status"], "ONLINE")
        self.assertEqual(agent["os_name"].lower(), "linux")
        self.assertTrue(agent["hostname"])
        self.assertTrue(agent["architecture"])
        self.assertEqual(probe.ack_state, "FULLY_APPLIED")

        ack = {
            "operation": "acknowledge",
            "operationId": probe.operation_id,
            "identifier": probe.operation_id,
            "operationState": {"state": probe.ack_state},
        }
        self.assertEqual(post_c2("acknowledge", ack), (204, b""))
        self.assertEqual(read_probe().acknowledged_at, probe.acknowledged_at)

        ack["operationState"]["state"] = "NOT_APPLIED"
        with self.assertRaises(HTTPError) as error:
            post_c2("acknowledge", ack)
        with error.exception as response:
            self.assertEqual(response.code, 409)
        self.assertEqual(read_probe().ack_state, "FULLY_APPLIED")

    def test_invalid_heartbeat_and_unknown_ack(self):
        with self.assertRaises(HTTPError) as error:
            post_c2("heartbeat", {"operation": "heartbeat", "agentInfo": {}})
        with error.exception as response:
            self.assertEqual(response.code, 422)

        with self.assertRaises(HTTPError) as error:
            post_c2("acknowledge", {
                "operation": "acknowledge",
                "operationId": str(uuid4()),
                "operationState": {"state": "FULLY_APPLIED"},
            })
        with error.exception as response:
            self.assertEqual(response.code, 404)

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
