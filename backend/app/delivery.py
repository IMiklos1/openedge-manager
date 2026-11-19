from datetime import datetime
import json

from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .catalog import MINIFI_VERSION
from .config import settings
from .models import Agent, Deployment, FlowArtifact

ACTIVE = ("PENDING", "DISPATCHED", "ACKNOWLEDGED")
DELIVERABLE = ("PENDING", "DISPATCHED")
SUCCESS_ACK = ("FULLY_APPLIED", "NO_OPERATION")
MANIFEST_COMPONENTS = "minifi_components"
EXECUTION_TYPES = {
    "org.apache.nifi.processors.standard.ExecuteProcess",
    "org.apache.nifi.processors.standard.ExecuteStreamCommand",
}


class ConfigurationArguments(BaseModel):
    flowId: str
    relativeFlowUrl: str


class UpdateConfiguration(BaseModel):
    identifier: str
    operation: str = "UPDATE"
    operand: str = "CONFIGURATION"
    args: ConfigurationArguments


def artifact_for(db: Session, deployment: Deployment) -> FlowArtifact:
    return db.get(FlowArtifact, (deployment.flow_id, deployment.flow_version))


def artifact_components(artifact: FlowArtifact) -> list[dict]:
    root = json.loads(artifact.content)["rootGroup"]
    return root["processors"] + root.get("controllerServices", [])


def permits_execution(components: list[dict]) -> bool:
    return settings.minifi_allow_execution_processors or all(item["type"] not in EXECUTION_TYPES for item in components)


def advertised_components(agent: Agent) -> set[tuple[str, ...]]:
    manifest = agent.capabilities.get(MANIFEST_COMPONENTS)
    if not isinstance(manifest, list):
        return set()
    return {tuple(entry) for entry in manifest if isinstance(entry, list) and len(entry) == 4
            and all(isinstance(value, str) and value for value in entry)}


def deployment_blocker(agent: Agent) -> str | None:
    if agent.id not in settings.flow_agent_ids:
        return "NOT_ENABLED"
    if agent.runtime != "minifi-java" or agent.runtime_version != MINIFI_VERSION:
        return "INCOMPATIBLE_RUNTIME"
    if not advertised_components(agent):
        return "AWAITING_MANIFEST"
    return None


def missing_agent_components(agent: Agent, components: list[dict]) -> list[str]:
    advertised = advertised_components(agent)
    return sorted({
        component["type"]
        for component in components
        if (component["type"], *(component["bundle"][key] for key in ("group", "artifact", "version"))) not in advertised
    })


def flow_update(
    db: Session, agent_id: str, reported_flow_id: str | None, seen_at: datetime,
) -> UpdateConfiguration | None:
    if agent_id not in settings.flow_agent_ids:
        return None
    deployment = db.scalar(
        select(Deployment).where(Deployment.agent_id == agent_id, Deployment.status.in_(ACTIVE)).with_for_update(),
    )
    if deployment is None:
        return None

    artifact = artifact_for(db, deployment)
    if deployment.status == "ACKNOWLEDGED":
        if reported_flow_id == artifact.sha256:
            deployment.status = "APPLIED"
            deployment.applied_at = seen_at
        return None

    components = artifact_components(artifact)
    if not permits_execution(components) or missing_agent_components(db.get(Agent, agent_id), components):
        return None
    deployment.status = "DISPATCHED"
    return UpdateConfiguration(
        identifier=deployment.id,
        args=ConfigurationArguments(
            flowId=artifact.sha256,
            relativeFlowUrl=f"configuration/{deployment.id}",
        ),
    )


def acknowledge_flow_update(
    db: Session, operation_id: str, agent_id: str | None, state: str, received_at: datetime,
) -> None:
    deployment = db.get(Deployment, operation_id, with_for_update=True)
    if (
        deployment is None
        or not deployment.agent_id
        or deployment.agent_id not in settings.flow_agent_ids
        or (agent_id is not None and agent_id != deployment.agent_id)
    ):
        raise HTTPException(404, "Unknown C2 operation")
    if deployment.ack_state is not None:
        if deployment.ack_state != state:
            raise HTTPException(409, "C2 operation already acknowledged with a different state")
        return
    if deployment.status != "DISPATCHED":
        raise HTTPException(409, "Flow update has not been dispatched")
    deployment.ack_state = state
    deployment.acknowledged_at = received_at
    deployment.status = "ACKNOWLEDGED" if state in SUCCESS_ACK else "FAILED"
