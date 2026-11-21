from datetime import datetime
import json

from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .runtimes import CPP, VERSIONS
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


class CppConfigurationArguments(BaseModel):
    flowId: str
    location: str
    persist: str = "true"


class UpdateConfiguration(BaseModel):
    identifier: str
    operation: str = "UPDATE"
    operand: str = "CONFIGURATION"
    args: ConfigurationArguments | CppConfigurationArguments


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
    if agent.runtime is None:
        return "AWAITING_MANIFEST"
    supported_version = VERSIONS.get(agent.runtime)
    if not supported_version or (agent.runtime_version and agent.runtime_version != supported_version):
        return "INCOMPATIBLE_RUNTIME"
    if not agent.runtime_version or not advertised_components(agent):
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
    db: Session, agent: Agent, reported_flow_id: str | None, seen_at: datetime,
) -> UpdateConfiguration | None:
    if deployment_blocker(agent) is not None:
        return None
    deployment = db.scalar(
        select(Deployment).where(Deployment.agent_id == agent.id, Deployment.status.in_(ACTIVE)).with_for_update(),
    )
    if deployment is None:
        return None

    artifact = artifact_for(db, deployment)
    if (agent.runtime, agent.runtime_version) != (artifact.runtime, artifact.runtime_version):
        return None
    if deployment.status == "ACKNOWLEDGED":
        if reported_flow_id == artifact.sha256:
            deployment.status = "APPLIED"
            deployment.applied_at = seen_at
        return None

    components = artifact_components(artifact)
    if not permits_execution(components) or missing_agent_components(agent, components):
        return None
    deployment.status = "DISPATCHED"
    path = f"configuration/{deployment.id}"
    args = (CppConfigurationArguments(flowId=artifact.sha256, location=path)
            if artifact.runtime == CPP else ConfigurationArguments(flowId=artifact.sha256, relativeFlowUrl=path))
    return UpdateConfiguration(identifier=deployment.id, args=args)


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
