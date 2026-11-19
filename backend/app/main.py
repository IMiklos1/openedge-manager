from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from fastapi import FastAPI, Depends, HTTPException, Query
from sqlalchemy import and_, case, func, select, text, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from .db import get_db
from .models import Agent, Flow, Deployment, FlowArtifact, FlowRevision
from .schemas import AgentHeartbeat, FlowCreate, FlowEdit, DeploymentCreate
from .catalog import MINIFI_VERSION, UNBUNDLED
from .compiler import CompileError, compile_minifi_java_json, runtime_validation
from .config import settings
from .delivery import ACTIVE, artifact_components, artifact_for, missing_agent_components, permits_execution
from .migrate import upgrade_schema
from .processor_properties import PROCESSOR_SCHEMAS, QUEUE_FIELDS, SERVICE_SCHEMAS, validate_secret_fields
from .c2 import router as minifi_c2_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    upgrade_schema()
    yield


app = FastAPI(title="OpenEdge Manager API", version="0.1.0", lifespan=lifespan)
app.include_router(minifi_c2_router)


@app.get("/health")
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(503, "Database unavailable") from exc
    return {"status": "ok", "service": "openedge-manager-api"}

@app.get("/api/v1/catalog")
def catalog():
    return {
        kind: {
            "category": schema["bundle"]["artifact"], "runtime": ["minifi-java"],
            "status": "SUPPORTED" if kind in {"GenerateFlowFile", "LogAttribute"} else "BUNDLED",
            "configuration": schema,
        }
        for kind, schema in PROCESSOR_SCHEMAS.items()
    } | {
        kind: {"category": category, "runtime": ["custom-extension"], "status": "NOT_BUNDLED"}
        for kind, category in UNBUNDLED.items()
    }


@app.get("/api/v1/flow-editor")
def flow_editor():
    return {"queue": QUEUE_FIELDS, "runtime_version": MINIFI_VERSION, "controller_services": SERVICE_SCHEMAS}

def agent_health(last_seen: datetime | None, recent: datetime) -> str:
    if last_seen is None:
        return "UNKNOWN"
    if last_seen.tzinfo is None:
        last_seen = last_seen.replace(tzinfo=timezone.utc)
    return "RECENT" if last_seen >= recent else "STALE"


@app.get("/api/v1/agents")
def list_agents(
    db: Session = Depends(get_db),
    agent_class: str | None = None,
    deployable: bool = False,
    q: str | None = Query(None, max_length=128),
    offset: int = Query(0, ge=0),
    limit: int | None = Query(None, ge=1, le=200),
):
    query = select(Agent).order_by(Agent.id).offset(offset).limit(limit)
    if agent_class:
        query = query.where(Agent.agent_class == agent_class)
    if deployable:
        query = query.where(Agent.id.in_(settings.flow_agent_ids),
                            Agent.runtime == "minifi-java", Agent.runtime_version == MINIFI_VERSION)
    if q:
        query = query.where(Agent.id.icontains(q, autoescape=True) | Agent.hostname.icontains(q, autoescape=True))
    rows = db.scalars(query).all()
    recent = datetime.now(timezone.utc) - timedelta(seconds=30)
    return [{
        "id": a.id, "hostname": a.hostname, "os_name": a.os_name,
        "architecture": a.architecture, "runtime": a.runtime,
        "runtime_version": a.runtime_version, "agent_class": a.agent_class,
        "status": a.status, "reported_flow_version": a.reported_flow_version,
        "can_deploy_flow": a.id in settings.flow_agent_ids and a.runtime == "minifi-java"
        and a.runtime_version == MINIFI_VERSION,
        "last_seen": a.last_seen.isoformat() if a.last_seen else None,
        "health": agent_health(a.last_seen, recent),
    } for a in rows]

@app.get("/api/v1/agent-classes")
def list_agent_classes(
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    recent = datetime.now(timezone.utc) - timedelta(seconds=30)
    counts = db.execute(
        select(Agent.agent_class, func.count(Agent.id), func.sum(case((Agent.last_seen >= recent, 1), else_=0)))
        .group_by(Agent.agent_class).order_by(Agent.agent_class).limit(limit).offset(offset),
    )
    return [{"name": name, "agents": total, "recent": healthy} for name, total, healthy in counts]


@app.post("/api/v1/agents/{agent_id}/heartbeat")
def oem_dev_heartbeat(agent_id: str, payload: AgentHeartbeat, db: Session = Depends(get_db)):
    # Development-only OEM API; not Apache MiNiFi C2.
    agent = db.get(Agent, agent_id) or Agent(id=agent_id)
    for key, value in payload.model_dump().items():
        setattr(agent, key, value)
    agent.status = "ONLINE"
    agent.last_seen = datetime.now(timezone.utc)
    db.add(agent)
    db.commit()
    return {"accepted": True, "agent_id": agent_id, "note": "OEM dev API, not MiNiFi C2"}

@app.get("/api/v1/flows")
def list_flows(
    db: Session = Depends(get_db),
    offset: int = Query(0, ge=0),
    limit: int | None = Query(None, ge=1, le=200),
):
    rows = db.scalars(select(Flow).order_by(Flow.name, Flow.id).offset(offset).limit(limit))
    return [{"id": f.id, "name": f.name, "version": f.current_version, "status": f.status} for f in rows]


def flow_definition(payload: FlowCreate | FlowEdit, flow_id: str) -> dict:
    definition = payload.definition.model_dump()
    if errors := validate_secret_fields(definition):
        raise HTTPException(422, errors)
    description = payload.description if payload.description is not None else definition["description"]
    return definition | {"flow_id": flow_id, "name": payload.name, "description": description}


def draft_result(flow_id: str, version: int, definition: dict) -> dict:
    errors, *_ = runtime_validation(definition)
    return {"id": flow_id, "version": version, "validation_errors": errors}


@app.post("/api/v1/flows")
def create_flow(payload: FlowCreate, db: Session = Depends(get_db)):
    definition = flow_definition(payload, payload.id)
    flow = Flow(id=payload.id, name=payload.name, description=definition["description"],
                current_version=1, definition=definition, status="DRAFT")
    db.add(flow)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        if db.get(Flow, payload.id):
            raise HTTPException(409, "Flow ID already exists") from exc
        raise
    db.add(FlowRevision(flow_id=flow.id, version=1, name=flow.name,
                        description=flow.description, definition=definition))
    db.commit()
    return draft_result(flow.id, 1, definition)


@app.put("/api/v1/flows/{flow_id}")
def edit_flow(flow_id: str, payload: FlowEdit, db: Session = Depends(get_db)):
    definition = flow_definition(payload, flow_id)
    next_version = payload.expected_version + 1
    result = db.execute(
        update(Flow).where(Flow.id == flow_id, Flow.current_version == payload.expected_version)
        .values(name=payload.name, description=definition["description"], current_version=next_version,
                definition=definition, status="DRAFT"),
    )
    if result.rowcount == 0:
        if db.get(Flow, flow_id) is None:
            raise HTTPException(404, "Flow not found")
        raise HTTPException(409, "Flow changed. Reload the latest revision before saving.")
    db.add(FlowRevision(flow_id=flow_id, version=next_version, name=payload.name,
                        description=definition["description"], definition=definition))
    db.commit()
    return draft_result(flow_id, next_version, definition)


@app.get("/api/v1/flows/{flow_id}")
def get_flow(flow_id: str, db: Session = Depends(get_db)):
    flow = db.get(Flow, flow_id)
    if not flow:
        raise HTTPException(404, "Flow not found")
    artifact = db.get(FlowArtifact, (flow_id, flow.current_version))
    return draft_result(flow.id, flow.current_version, flow.definition) | {
        "name": flow.name, "description": flow.description, "status": flow.status,
        "definition": flow.definition, "published_sha256": artifact.sha256 if artifact else None,
    }


@app.get("/api/v1/flows/{flow_id}/versions")
def flow_versions(
    flow_id: str,
    db: Session = Depends(get_db),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    if db.get(Flow, flow_id) is None:
        raise HTTPException(404, "Flow not found")
    rows = db.execute(
        select(FlowRevision, FlowArtifact.sha256)
        .outerjoin(FlowArtifact, and_(FlowRevision.flow_id == FlowArtifact.flow_id,
                                     FlowRevision.version == FlowArtifact.version))
        .where(FlowRevision.flow_id == flow_id).order_by(FlowRevision.version.desc()).offset(offset).limit(limit),
    )
    return [{"version": revision.version, "name": revision.name,
             "created_at": revision.created_at, "sha256": digest} for revision, digest in rows]


@app.get("/api/v1/flows/{flow_id}/versions/{version}")
def flow_version(flow_id: str, version: int, db: Session = Depends(get_db)):
    revision = db.get(FlowRevision, (flow_id, version))
    if revision is None:
        raise HTTPException(404, "Flow version not found")
    artifact = db.get(FlowArtifact, (flow_id, version))
    return draft_result(flow_id, version, revision.definition) | {
        "name": revision.name, "description": revision.description,
        "status": "PUBLISHED" if artifact else "DRAFT", "definition": revision.definition,
        "published_sha256": artifact.sha256 if artifact else None,
    }


@app.post("/api/v1/flows/{flow_id}/publish")
def publish_flow(flow_id: str, db: Session = Depends(get_db), version: int | None = Query(None, ge=1)):
    flow = db.get(Flow, flow_id, with_for_update=True)
    if not flow:
        raise HTTPException(404, "Flow not found")
    if version is not None and version != flow.current_version:
        raise HTTPException(409, "Flow changed. Reload the latest revision before publishing.")
    artifact = db.get(FlowArtifact, (flow.id, flow.current_version))
    if artifact is None:
        try:
            content = compile_minifi_java_json(flow.definition | {"flow_id": flow.id, "name": flow.name})
        except CompileError as exc:
            raise HTTPException(422, str(exc)) from exc
        artifact = FlowArtifact(
            flow_id=flow.id,
            version=flow.current_version,
            runtime_version=MINIFI_VERSION,
            sha256=sha256(content.encode()).hexdigest(),
            content=content,
        )
        db.add(artifact)
    flow.status = "PUBLISHED"
    db.commit()
    return {"id": flow.id, "version": flow.current_version, "status": flow.status,
            "sha256": artifact.sha256, "runtime_version": artifact.runtime_version}


def deployment_result(deployment: Deployment, artifact: FlowArtifact | None) -> dict:
    return {
        "id": deployment.id,
        "flow_id": deployment.flow_id,
        "version": deployment.flow_version,
        "target_class": deployment.target_class,
        "agent_id": deployment.agent_id,
        "status": deployment.status,
        "sha256": artifact.sha256 if artifact else None,
        "ack_state": deployment.ack_state,
        "acknowledged_at": deployment.acknowledged_at,
        "applied_at": deployment.applied_at,
        "created_at": deployment.created_at,
    }


@app.post("/api/v1/deployments")
def create_deployment(payload: DeploymentCreate, db: Session = Depends(get_db)):
    flow = db.get(Flow, payload.flow_id)
    if not flow:
        raise HTTPException(404, "Flow not found")
    version = payload.version or flow.current_version
    if payload.version is None and flow.status != "PUBLISHED":
        raise HTTPException(409, "Flow must be published before deployment")
    if payload.version is not None and db.get(FlowArtifact, (flow.id, version)) is None:
        raise HTTPException(409, "The specified flow version has not been published")
    deployment = Deployment(flow_id=flow.id, flow_version=version, status="PENDING")
    if payload.agent_id is None:
        if payload.target_class is None:
            raise HTTPException(422, "Select an agent or provide a target class")
        deployment.target_class = payload.target_class
        db.add(deployment)
        db.commit()
        return deployment_result(deployment, None) | {"note": "Class-wide deployment is metadata only."}

    if payload.agent_id not in settings.flow_agent_ids:
        raise HTTPException(403, "Flow updates are enabled only for configured agents")
    agent = db.get(Agent, payload.agent_id)
    if agent is None:
        raise HTTPException(404, "Agent has not checked in")
    if agent.runtime != "minifi-java" or agent.runtime_version != MINIFI_VERSION:
        raise HTTPException(409, f"Agent must report MiNiFi Java {MINIFI_VERSION}")
    artifact = artifact_for(db, deployment)
    if artifact is None:
        raise HTTPException(409, "Publish a compiled flow artifact before deployment")
    components = artifact_components(artifact)
    if not permits_execution(components):
        raise HTTPException(403, "The target is not enabled for command execution processors")
    if missing := missing_agent_components(agent, components):
        raise HTTPException(409, "Agent manifest is missing required components: " + ", ".join(missing))
    deployment.agent_id = agent.id
    deployment.target_class = agent.agent_class
    db.add(deployment)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if db.scalar(select(Deployment.id).where(Deployment.agent_id == agent.id, Deployment.status.in_(ACTIVE))):
            raise HTTPException(409, "Agent already has an active flow deployment") from exc
        raise
    return deployment_result(deployment, artifact)


@app.get("/api/v1/deployments")
def list_deployments(
    db: Session = Depends(get_db),
    flow_id: str | None = None,
    agent_id: str | None = None,
    status: str | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    query = (
        select(Deployment, FlowArtifact, FlowRevision.name)
        .outerjoin(FlowArtifact, and_(Deployment.agent_id.is_not(None),
                                     Deployment.flow_id == FlowArtifact.flow_id,
                                     Deployment.flow_version == FlowArtifact.version))
        .outerjoin(FlowRevision, and_(Deployment.flow_id == FlowRevision.flow_id,
                                     Deployment.flow_version == FlowRevision.version))
        .order_by(Deployment.created_at.desc(), Deployment.id.desc()).offset(offset).limit(limit)
    )
    for column, value in ((Deployment.flow_id, flow_id), (Deployment.agent_id, agent_id),
                          (Deployment.status, status)):
        if value:
            query = query.where(column == value)
    return [deployment_result(deployment, artifact) | {"flow_name": name}
            for deployment, artifact, name in db.execute(query)]


@app.get("/api/v1/deployments/{deployment_id}")
def get_deployment(deployment_id: str, db: Session = Depends(get_db)):
    deployment = db.get(Deployment, deployment_id)
    if deployment is None:
        raise HTTPException(404, "Deployment not found")
    artifact = artifact_for(db, deployment) if deployment.agent_id else None
    return deployment_result(deployment, artifact)
