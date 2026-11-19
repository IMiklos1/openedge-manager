import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Integer, Text, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base

def now():
    return datetime.now(timezone.utc)

class Agent(Base):
    __tablename__ = "agents"
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    hostname: Mapped[str | None] = mapped_column(String(255), nullable=True)
    os_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    architecture: Mapped[str | None] = mapped_column(String(50), nullable=True)
    runtime: Mapped[str | None] = mapped_column(String(100), nullable=True)
    runtime_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    agent_class: Mapped[str] = mapped_column(String(100), default="unassigned")
    status: Mapped[str] = mapped_column(String(30), default="UNKNOWN")
    reported_flow_version: Mapped[int] = mapped_column(Integer, default=0)
    capabilities: Mapped[dict] = mapped_column(JSON, default=dict)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class C2Probe(Base):
    __tablename__ = "c2_probes"
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"), primary_key=True)
    operation_id: Mapped[str] = mapped_column(String(36), unique=True)
    ack_state: Mapped[str | None] = mapped_column(String(32))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Flow(Base):
    __tablename__ = "flows"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_version: Mapped[int] = mapped_column(Integer, default=1)
    definition: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(30), default="DRAFT")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class FlowArtifact(Base):
    __tablename__ = "flow_artifacts"
    flow_id: Mapped[str] = mapped_column(ForeignKey("flows.id"), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    runtime_version: Mapped[str] = mapped_column(String(100))
    sha256: Mapped[str] = mapped_column(String(64))
    content: Mapped[str] = mapped_column(Text)


class Deployment(Base):
    __tablename__ = "deployments"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    flow_id: Mapped[str] = mapped_column(ForeignKey("flows.id"))
    flow_version: Mapped[int] = mapped_column(Integer)
    target_class: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(30), default="PENDING")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    agent_id: Mapped[str | None] = mapped_column(ForeignKey("agents.id"))
    ack_state: Mapped[str | None] = mapped_column(String(32))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FlowRevision(Base):
    __tablename__ = "flow_revisions"
    flow_id: Mapped[str] = mapped_column(ForeignKey("flows.id"), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    definition: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
