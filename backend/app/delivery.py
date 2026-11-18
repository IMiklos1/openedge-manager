from datetime import datetime

from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .models import Deployment, FlowArtifact

ACTIVE = ("PENDING", "DISPATCHED", "ACKNOWLEDGED")
DELIVERABLE = ("PENDING", "DISPATCHED")
SUCCESS_ACK = ("FULLY_APPLIED", "NO_OPERATION")


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


def flow_update(
    db: Session, agent_id: str, reported_flow_id: str | None, seen_at: datetime,
) -> UpdateConfiguration | None:
    if agent_id != settings.minifi_flow_agent_id:
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
        or deployment.agent_id != settings.minifi_flow_agent_id
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
