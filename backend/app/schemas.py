from typing import Any, Literal
from pydantic import BaseModel, Field, ConfigDict

class AgentHeartbeat(BaseModel):
    hostname: str | None = None
    os_name: str | None = None
    architecture: str | None = None
    runtime: str | None = "minifi-cpp"
    runtime_version: str | None = None
    agent_class: str = "unassigned"
    reported_flow_version: int = 0
    capabilities: dict[str, Any] = Field(default_factory=dict)

class NodeConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    type: str
    label: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)

class Connection(BaseModel):
    id: str
    source: str
    source_relationship: str = "success"
    target: str

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
    id: str
    name: str
    description: str | None = None
    definition: FlowDefinition

class DeploymentCreate(BaseModel):
    flow_id: str
    target_class: str
