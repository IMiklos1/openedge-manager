from datetime import datetime, timezone
from typing import Annotated, Literal, TypeVar
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, StringConstraints, ValidationError
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import Agent, C2Probe

router = APIRouter(prefix="/c2-protocol", tags=["MiNiFi C2"])
MAX_BODY_BYTES = 4 * 1024 * 1024
AgentId = Annotated[str, StringConstraints(min_length=1, max_length=128, pattern=r"^[^\x00-\x20\x7f]+$")]
RuntimeVersion = Annotated[str, StringConstraints(max_length=100, pattern=r"^[^\x00]*$")]
AckState = Literal["FULLY_APPLIED", "PARTIALLY_APPLIED", "OPERATION_NOT_UNDERSTOOD", "NO_OPERATION", "NOT_APPLIED"]


class BuildInfo(BaseModel):
    version: RuntimeVersion | None = None


class AgentManifest(BaseModel):
    agentType: Literal["minifi-java"] | None = None
    version: RuntimeVersion | None = None
    buildInfo: BuildInfo | None = None


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


class Heartbeat(BaseModel):
    agentInfo: AgentInfo
    deviceInfo: DeviceInfo | None = None


class OperationState(BaseModel):
    state: AckState


class Acknowledgement(BaseModel):
    operationId: AgentId
    operationState: OperationState


class DescribeManifest(BaseModel):
    identifier: str
    operation: Literal["DESCRIBE"] = "DESCRIBE"
    operand: Literal["MANIFEST"] = "MANIFEST"


class HeartbeatResponse(BaseModel):
    requestedOperations: list[DescribeManifest]


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
    version = manifest.version if manifest else None
    reported_values = {
        "agent_class": info.agentClass,
        "runtime_version": version or (build.version if build else None),
        "hostname": network.hostname if network else None,
        "os_name": system.operatingSystem if system else None,
        "architecture": system.machineArch if system else None,
    }
    values = {key: value for key, value in reported_values.items() if value}
    values.update(runtime="minifi-java", status="ONLINE", last_seen=datetime.now(timezone.utc))
    insert = pg_insert if db.get_bind().dialect.name == "postgresql" else sqlite_insert
    db.execute(insert(Agent).values(id=info.identifier, **values).on_conflict_do_update(
        index_elements=[Agent.id], set_=values,
    ))

    operations = []
    if info.identifier == settings.minifi_probe_agent_id:
        # One read-only probe per configured agent. Preserve the ID across retries.
        db.execute(insert(C2Probe).values(agent_id=info.identifier, operation_id=str(uuid4())).on_conflict_do_nothing(
            index_elements=[C2Probe.agent_id],
        ))
        probe = db.get(C2Probe, info.identifier)
        if probe.ack_state is None:
            operations.append(DescribeManifest(identifier=probe.operation_id))
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
    updated = db.execute(
        update(C2Probe).where(operation, C2Probe.ack_state.is_(None))
        .values(ack_state=state, acknowledged_at=datetime.now(timezone.utc)),
    )
    if updated.rowcount == 0:
        previous_state = db.scalar(select(C2Probe.ack_state).where(operation))
        if previous_state is None:
            raise HTTPException(404, "Unknown C2 operation")
        if previous_state != state:
            raise HTTPException(409, "C2 operation already acknowledged with a different state")
    db.commit()
    return Response(status_code=204)
