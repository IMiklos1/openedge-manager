from contextlib import asynccontextmanager
from datetime import datetime, timezone
from hashlib import sha256
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from .db import get_db
from .models import Agent, Flow, Deployment, FlowArtifact
from .schemas import AgentHeartbeat, FlowCreate, DeploymentCreate
from .catalog import CATALOG
from .compiler import CompileError, MINIFI_VERSION, compile_minifi_java_json, validate_flow
from .config import settings
from .delivery import ACTIVE, artifact_for
from .migrate import upgrade_schema
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
    return CATALOG

@app.get("/api/v1/agents")
def list_agents(db: Session = Depends(get_db)):
    rows = db.query(Agent).order_by(Agent.id).all()
    return [{
        "id": a.id, "hostname": a.hostname, "os_name": a.os_name,
        "architecture": a.architecture, "runtime": a.runtime,
        "runtime_version": a.runtime_version, "agent_class": a.agent_class,
        "status": a.status, "reported_flow_version": a.reported_flow_version,
        "can_deploy_flow": a.id == settings.minifi_flow_agent_id and a.runtime == "minifi-java"
        and a.runtime_version == MINIFI_VERSION,
        "last_seen": a.last_seen.isoformat() if a.last_seen else None
    } for a in rows]

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
def list_flows(db: Session = Depends(get_db)):
    return [{"id": f.id, "name": f.name, "version": f.current_version, "status": f.status}
            for f in db.query(Flow).order_by(Flow.name).all()]

@app.post("/api/v1/flows")
def create_flow(payload: FlowCreate, db: Session = Depends(get_db)):
    if db.get(Flow, payload.id):
        raise HTTPException(409, "Flow ID already exists")
    definition = payload.definition.model_dump()
    errors = validate_flow(definition)
    flow = Flow(id=payload.id, name=payload.name, description=payload.description,
                current_version=1, definition=definition, status="DRAFT")
    db.add(flow)
    db.commit()
    return {"id": flow.id, "version": flow.current_version, "validation_errors": errors}

@app.get("/api/v1/flows/{flow_id}")
def get_flow(flow_id: str, db: Session = Depends(get_db)):
    flow = db.get(Flow, flow_id)
    if not flow:
        raise HTTPException(404, "Flow not found")
    return {"id": flow.id, "name": flow.name, "version": flow.current_version,
            "status": flow.status, "definition": flow.definition,
            "validation_errors": validate_flow(flow.definition)}

@app.post("/api/v1/flows/{flow_id}/publish")
def publish_flow(flow_id: str, db: Session = Depends(get_db)):
    flow = db.get(Flow, flow_id, with_for_update=True)
    if not flow:
        raise HTTPException(404, "Flow not found")
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
    }


@app.post("/api/v1/deployments")
def create_deployment(payload: DeploymentCreate, db: Session = Depends(get_db)):
    flow = db.get(Flow, payload.flow_id)
    if not flow:
        raise HTTPException(404, "Flow not found")
    if flow.status != "PUBLISHED":
        raise HTTPException(409, "Flow must be published before deployment")
    deployment = Deployment(flow_id=flow.id, flow_version=flow.current_version, status="PENDING")
    if payload.agent_id is None:
        if payload.target_class is None:
            raise HTTPException(422, "Select an agent or provide a target class")
        deployment.target_class = payload.target_class
        db.add(deployment)
        db.commit()
        return deployment_result(deployment, None) | {"note": "Class-wide deployment is metadata only."}

    if payload.agent_id != settings.minifi_flow_agent_id:
        raise HTTPException(403, "Flow updates are enabled only for the configured development agent")
    agent = db.get(Agent, payload.agent_id)
    if agent is None:
        raise HTTPException(404, "Agent has not checked in")
    if agent.runtime != "minifi-java" or agent.runtime_version != MINIFI_VERSION:
        raise HTTPException(409, f"Agent must report MiNiFi Java {MINIFI_VERSION}")
    artifact = artifact_for(db, deployment)
    if artifact is None:
        raise HTTPException(409, "Publish a compiled flow artifact before deployment")
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


@app.get("/api/v1/deployments/{deployment_id}")
def get_deployment(deployment_id: str, db: Session = Depends(get_db)):
    deployment = db.get(Deployment, deployment_id)
    if deployment is None:
        raise HTTPException(404, "Deployment not found")
    artifact = artifact_for(db, deployment) if deployment.agent_id else None
    return deployment_result(deployment, artifact)
