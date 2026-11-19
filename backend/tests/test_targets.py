import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.catalog import MINIFI_VERSION
from app.config import Settings, settings
from app.db import Base
from app.delivery import MANIFEST_COMPONENTS
from app.main import list_agents
from app.models import Agent


class DeploymentTargetsTest(unittest.TestCase):
    def test_compose_fallback_and_explicit_ids(self):
        defaults = {
            "minifi_flow_agent_id": "",
            "minifi_flow_agent_ids": "",
            "minifi_enable_compose_test_targets": True,
        }
        cases = (
            ({}, {"oem-test-agent-01", "oem-test-agent-02"}),
            ({"minifi_enable_compose_test_targets": False}, set()),
            ({"minifi_flow_agent_id": " lab-01 "}, {"lab-01"}),
            ({"minifi_flow_agent_id": "lab-01", "minifi_flow_agent_ids": " lab-02 ,lab-01,"}, {"lab-01", "lab-02"}),
        )
        for overrides, expected in cases:
            with self.subTest(overrides=overrides):
                config = Settings(_env_file=None, **(defaults | overrides))
                self.assertEqual(config.flow_agent_ids, expected)

    def test_inventory_retains_blocked_targets_and_filtered_list_pages_ready_targets(self):
        engine = create_engine("sqlite://")
        self.addCleanup(engine.dispose)
        Base.metadata.create_all(engine)
        manifest = {MANIFEST_COMPONENTS: [["processor", "group", "bundle", MINIFI_VERSION]]}
        with Session(engine) as db, patch.object(
            settings, "minifi_flow_agent_ids", "a-awaiting,b-ready,c-incompatible",
        ):
            db.add_all([
                Agent(id="a-awaiting", runtime="minifi-java", runtime_version=MINIFI_VERSION,
                      capabilities={MANIFEST_COMPONENTS: []}),
                Agent(id="b-ready", runtime="minifi-java", runtime_version=MINIFI_VERSION, capabilities=manifest),
                Agent(id="c-incompatible", runtime="minifi-java", runtime_version="0.0"),
                Agent(id="d-disabled", runtime="minifi-java", runtime_version=MINIFI_VERSION, capabilities=manifest),
            ])
            db.commit()
            agents = list_agents(db, offset=0, limit=None, q=None)
            self.assertEqual({item["id"]: item["deployment_blocker"] for item in agents}, {
                "a-awaiting": "AWAITING_MANIFEST",
                "b-ready": None,
                "c-incompatible": "INCOMPATIBLE_RUNTIME",
                "d-disabled": "NOT_ENABLED",
            })
            self.assertEqual([item["id"] for item in agents if item["can_deploy_flow"]], ["b-ready"])
            ready = list_agents(db, deployable=True, offset=0, limit=1, q=None)
            self.assertEqual([item["id"] for item in ready], ["b-ready"])
