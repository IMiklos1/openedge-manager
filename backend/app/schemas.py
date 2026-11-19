from typing import Any, Literal
from pydantic import BaseModel, Field, ConfigDict

class AgentHeartbeat(BaseModel):
    hostname: str | None = None
    os_name: str | None = None
    architecture: str | None = None
    runtime: str | None = "minifi-java"
    runtime_version: str | None = None
    agent_class: str = "unassigned"
    reported_flow_version: int = 0
    capabilities: dict[str, Any] = Field(default_factory=dict)

class Position(BaseModel):
    x: float = Field(allow_inf_nan=False)
    y: float = Field(allow_inf_nan=False)


class NodeConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    type: str
    label: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    position: Position | None = None
    description: str | None = None
    scheduling: dict[str, Any] = Field(default_factory=dict)
    attributes: dict[str, str] = Field(default_factory=dict)
    auto_terminate_success: bool | None = None

class Connection(BaseModel):
    id: str
    source: str
    source_relationship: str = "success"
    target: str
    label: str | None = None
    queue: dict[str, Any] = Field(default_factory=dict)

class FlowDefinition(BaseModel):
    schema_version: Literal["1.0"]
    flow_id: str
    name: str
    description: str | None = None
    target_class: str = "unassigned"
    nodes: list[NodeConfig]
    connections: list[Connection]
    parameters: dict[str, Any] = Field(default_factory=dict)

class FlowCreate(BaseModel):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[^\x00]+$")
    name: str = Field(min_length=1, max_length=255, pattern=r"^[^\x00]+$")
    description: str | None = None
    definition: FlowDefinition

class FlowEdit(BaseModel):
    expected_version: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=255, pattern=r"^[^\x00]+$")
    description: str | None = None
    definition: FlowDefinition


class DeploymentCreate(BaseModel):
    flow_id: str
    version: int | None = Field(default=None, ge=1)
    target_class: str | None = Field(default=None, min_length=1, max_length=100)
    agent_id: str | None = Field(default=None, min_length=1, max_length=128)
