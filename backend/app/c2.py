import logging
from datetime import datetime, timezone
from typing import Annotated, Literal, TypeVar
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, StringConstraints, ValidationError
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from .runtimes import CPP, JAVA
from .config import settings
from .db import get_db
from .models import Agent, C2Probe, Deployment
from .delivery import (
    MANIFEST_COMPONENTS, UpdateConfiguration, acknowledge_flow_update,
    artifact_components, artifact_for, flow_update, permits_execution,
)

router = APIRouter(prefix="/c2-protocol", tags=["MiNiFi C2"])
logger = logging.getLogger(__name__)
MAX_BODY_BYTES = 4 * 1024 * 1024
AgentId = Annotated[str, StringConstraints(min_length=1, max_length=128, pattern=r"^[^\x00-\x20\x7f]+$")]
RuntimeVersion = Annotated[str, StringConstraints(max_length=100, pattern=r"^[^\x00]*$")]
AckState = Literal["FULLY_APPLIED", "PARTIALLY_APPLIED", "OPERATION_NOT_UNDERSTOOD", "NO_OPERATION", "NOT_APPLIED"]


class BuildInfo(BaseModel):
    version: RuntimeVersion | None = None


class Extension(BaseModel):
    type: Annotated[str, StringConstraints(min_length=1, max_length=512, pattern=r"^[^\x00]+$")]


class ComponentManifest(BaseModel):
    processors: list[Extension] | None = None
    controllerServices: list[Extension] | None = None


class AgentBundle(BaseModel):
    group: RuntimeVersion
    artifact: RuntimeVersion
    version: RuntimeVersion
    componentManifest: ComponentManifest | None = None


class AgentManifest(BaseModel):
    agentType: RuntimeVersion | None = None
    version: RuntimeVersion | None = None
    buildInfo: BuildInfo | None = None
    bundles: list[AgentBundle] | None = None


class AgentInfo(BaseModel):
    identifier: AgentId
    agentClass: Annotated[str, StringConstraints(max_length=100, pattern=r"^[^\x00]*$")] | None = None
    agentManifest: AgentManifest | None = None


class SystemInfo(BaseModel):
    operatingSystem: Annotated[str, StringConstraints(max_length=100, pattern=r"^[^\x00]*$")] | None = None
    machineArch: Annotated[str, StringConstraints(max_length=50, pattern=r"^[^\x00]*$")] | None = None


class NetworkInfo(BaseModel):
    hostname: Annotated[str, StringConstraints(max_length=255, pattern=r"^[^\x00]*$")] | None = None


class DeviceInfo(BaseModel):
    systemInfo: SystemInfo | None = None
    networkInfo: NetworkInfo | None = None


class FlowInfo(BaseModel):
    flowId: str | None = None
    runStatus: Literal["RUNNING", "STOPPED"] | None = None


class Heartbeat(BaseModel):
    agentInfo: AgentInfo
    deviceInfo: DeviceInfo | None = None
    flowInfo: FlowInfo | None = None


class OperationState(BaseModel):
    state: AckState


class AcknowledgingAgent(BaseModel):
    identifier: AgentId


class Acknowledgement(BaseModel):
    operationId: AgentId
    operationState: OperationState
    agentInfo: AcknowledgingAgent | None = None


class DescribeManifest(BaseModel):
    identifier: str
    operation: Literal["DESCRIBE"] = "DESCRIBE"
    operand: Literal["MANIFEST"] = "MANIFEST"


class HeartbeatResponse(BaseModel):
    requestedOperations: list[DescribeManifest | UpdateConfiguration]


async def read_c2_body(request: Request) -> bytearray:
    if request.headers.get("content-encoding", "identity").lower() != "identity":
        raise HTTPException(415, "C2 supports uncompressed JSON")
    media_type = request.headers.get("content-type", "").partition(";")[0].strip().lower()
    if media_type != "application/json":
        raise HTTPException(415, "C2 requires application/json")
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_BODY_BYTES:
            raise HTTPException(413, "C2 message exceeds the size limit")
        body.extend(chunk)
    return body


Message = TypeVar("Message", bound=BaseModel)


def parse_c2_message(model: type[Message], body: bytearray) -> Message:
    try:
        return model.model_validate_json(body)
    except ValidationError as exc:
        error = exc.errors(include_input=False, include_context=False, include_url=False)[0]
        field = ".".join(map(str, error["loc"])) or "<body>"
        logger.warning("Invalid C2 %s: field=%s type=%s", model.__name__, field, error["type"])
        if error["type"] == "json_invalid":
            try:
                body.decode("utf-8")
            except UnicodeDecodeError as encoding_error:
                logger.warning("Invalid C2 UTF-8 at byte %d", encoding_error.start)
        raise HTTPException(422, "Invalid C2 message") from exc


@router.post("/heartbeat", response_model=HeartbeatResponse)
def heartbeat(
    body: Annotated[bytearray, Depends(read_c2_body)],
    db: Annotated[Session, Depends(get_db)],
):
    payload = parse_c2_message(Heartbeat, body)
    info = payload.agentInfo
    manifest = info.agentManifest
    device = payload.deviceInfo
    system = device.systemInfo if device else None
    network = device.networkInfo if device else None
    build = manifest.buildInfo if manifest else None
    # Full manifests identify the implementation. Lightweight heartbeats preserve it.
    runtime = {"minifi-java": JAVA, "cpp": CPP}.get(manifest.agentType, "unknown") if manifest and manifest.agentType else None
    previous = db.get(Agent, info.identifier) if runtime is not None else None
    version = (manifest.version or (build.version if build else None)) if runtime is not None else None
    reported_values = {
        "agent_class": info.agentClass,
        "runtime_version": version,
        "runtime": runtime,
        "hostname": network.hostname if network else None,
        "os_name": system.operatingSystem if system else None,
        "architecture": system.machineArch if system else None,
    }
    values = {key: value for key, value in reported_values.items() if value}
    if previous is not None and previous.runtime != runtime:
        values.update(runtime_version=version, capabilities={})
    if runtime in (JAVA, CPP) and manifest.bundles is not None:
        # Store only component identities, omitting descriptions, configuration and other wire metadata.
        extensions = []
        for bundle in manifest.bundles:
            if bundle.componentManifest is None:
                continue
            coordinates = [bundle.group, bundle.artifact, bundle.version]
            for entry in (bundle.componentManifest.processors or []) + (bundle.componentManifest.controllerServices or []):
                extensions.append([entry.type, *coordinates])
        values["capabilities"] = {MANIFEST_COMPONENTS: sorted(extensions)}
    seen_at = datetime.now(timezone.utc)
    values.update(status="ONLINE", last_seen=seen_at)
    insert = pg_insert if db.get_bind().dialect.name == "postgresql" else sqlite_insert
    result = db.execute(insert(Agent).values(id=info.identifier, **values).on_conflict_do_update(
        index_elements=[Agent.id], set_=values,
    ).returning(Agent), execution_options={"populate_existing": True})
    agent = result.scalar_one()

    operations = []
    if info.identifier == settings.minifi_probe_agent_id:
        # One read-only probe per configured agent. Preserve the ID across retries.
        db.execute(insert(C2Probe).values(agent_id=info.identifier, operation_id=str(uuid4())).on_conflict_do_nothing(
            index_elements=[C2Probe.agent_id],
        ))
        probe = db.get(C2Probe, info.identifier)
        if probe.ack_state is None:
            operations.append(DescribeManifest(identifier=probe.operation_id))
    running_flow = payload.flowInfo.flowId if payload.flowInfo and payload.flowInfo.runStatus == "RUNNING" else None
    command = flow_update(db, agent, running_flow, seen_at)
    if command is not None:
        operations.append(command)
    db.commit()
    return HeartbeatResponse(requestedOperations=operations)


@router.post("/acknowledge", status_code=204)
def acknowledge(
    body: Annotated[bytearray, Depends(read_c2_body)],
    db: Annotated[Session, Depends(get_db)],
):
    ack = parse_c2_message(Acknowledgement, body)
    state = ack.operationState.state
    operation = C2Probe.operation_id == ack.operationId
    if ack.agentInfo is not None:
        operation = operation & (C2Probe.agent_id == ack.agentInfo.identifier)
    received_at = datetime.now(timezone.utc)
    updated = db.execute(
        update(C2Probe).where(operation, C2Probe.ack_state.is_(None))
        .values(ack_state=state, acknowledged_at=received_at),
    )
    if updated.rowcount == 0:
        previous_state = db.scalar(select(C2Probe.ack_state).where(operation))
        if previous_state is None:
            agent_id = ack.agentInfo.identifier if ack.agentInfo else None
            acknowledge_flow_update(db, ack.operationId, agent_id, state, received_at)
        elif previous_state != state:
            raise HTTPException(409, "C2 operation already acknowledged with a different state")
    db.commit()
    return Response(status_code=204)


@router.get("/configuration/{operation_id}")
def download_configuration(operation_id: AgentId, db: Annotated[Session, Depends(get_db)]):
    deployment = db.get(Deployment, operation_id)
    if (
        deployment is None
        or not deployment.agent_id
        or deployment.agent_id not in settings.flow_agent_ids
        or deployment.status != "DISPATCHED"
    ):
        raise HTTPException(404, "No configuration for this operation")
    artifact = artifact_for(db, deployment)
    if not permits_execution(artifact_components(artifact)):
        raise HTTPException(404, "No configuration for this operation")
    return Response(
        artifact.content,
        media_type="application/json",
        headers={"ETag": f'"{artifact.sha256}"', "Cache-Control": "no-store"},
    )
