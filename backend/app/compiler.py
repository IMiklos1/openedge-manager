import json
from uuid import NAMESPACE_URL, uuid5

from .catalog import CATALOG

class CompileError(ValueError):
    pass

def validate_flow(definition: dict) -> list[str]:
    errors = []
    nodes = definition.get("nodes", [])
    ids = {n.get("id") for n in nodes}
    if len(ids) != len(nodes):
        errors.append("Node IDs must be unique.")
    for node in nodes:
        kind = node.get("type")
        if kind not in CATALOG:
            errors.append(f"Unknown processor type: {kind}")
        elif CATALOG[kind]["status"] == "NOT_IMPLEMENTED":
            errors.append(f"{kind} requires a custom extension and is not deployable yet.")
    for edge in definition.get("connections", []):
        if edge.get("source") not in ids:
            errors.append(f"Connection {edge.get('id')} references missing source.")
        if edge.get("target") not in ids:
            errors.append(f"Connection {edge.get('id')} references missing target.")
    return errors

MINIFI_VERSION = "2.12.0"
SUPPORTED_PROCESSORS = {
    "GenerateFlowFile": {"File Size": "1 B", "Batch Size": "1", "Data Format": "Binary"},
    "LogAttribute": {"Log Level": "info", "Log Payload": "false"},
}


def component_id(flow_id: str, *parts: str) -> str:
    return str(uuid5(NAMESPACE_URL, json.dumps(["openedge-manager", flow_id, *parts])))


def compile_minifi_java_json(definition: dict) -> str:
    errors = validate_flow(definition)
    nodes = definition["nodes"]
    connections = definition["connections"]
    if not nodes or len(nodes) > 20 or len(connections) > 40:
        errors.append("Use 1–20 processors and at most 40 connections.")
    if definition["parameters"]:
        errors.append("Flow parameters are unsupported by the test compiler.")
    for node in nodes:
        if node["type"] not in SUPPORTED_PROCESSORS:
            errors.append(f"Node {node['id']}: {node['type']} is unsupported by the test compiler.")
        if node["config"]:
            errors.append(f"Node {node['id']}: custom properties are unsupported.")
    if errors:
        raise CompileError("; ".join(errors))

    kinds = {node["id"]: node["type"] for node in nodes}
    sinks = {edge["target"] for edge in connections}
    if not any(kind == "GenerateFlowFile" for kind in kinds.values()):
        errors.append("Add at least one GenerateFlowFile processor.")
    if any(kind == "LogAttribute" and node_id not in sinks for node_id, kind in kinds.items()):
        errors.append("Each LogAttribute processor needs an incoming connection.")
    if len({edge["id"] for edge in connections}) != len(connections):
        errors.append("Connection IDs must be unique.")
    for edge in connections:
        if (kinds[edge["source"]], kinds[edge["target"]], edge["source_relationship"]) != (
            "GenerateFlowFile", "LogAttribute", "success",
        ):
            errors.append(f"Connection {edge['id']}: use GenerateFlowFile → LogAttribute over success.")
    if errors:
        raise CompileError("; ".join(errors))

    flow_id = definition["flow_id"]
    group_id = component_id(flow_id, "root")
    connected = {edge["source"] for edge in connections}
    processors = []
    for index, node in enumerate(nodes):
        kind = node["type"]
        processor_id = component_id(flow_id, "processor", node["id"])
        processors.append({
            "identifier": processor_id,
            "instanceIdentifier": processor_id,
            "name": node.get("label") or kind,
            "position": {"x": float(index * 300), "y": 0.0},
            "type": f"org.apache.nifi.processors.standard.{kind}",
            "bundle": {"group": "org.apache.nifi.minifi", "artifact": "minifi-standard-nar", "version": MINIFI_VERSION},
            "properties": SUPPORTED_PROCESSORS[kind],
            "propertyDescriptors": {},
            "style": {},
            "schedulingPeriod": "5 sec" if kind == "GenerateFlowFile" else "1 sec",
            "schedulingStrategy": "TIMER_DRIVEN",
            "executionNode": "ALL",
            "penaltyDuration": "30 sec",
            "yieldDuration": "1 sec",
            "bulletinLevel": "WARN",
            "runDurationMillis": 0,
            "concurrentlySchedulableTaskCount": 1,
            "autoTerminatedRelationships": [] if node["id"] in connected else ["success"],
            "scheduledState": "RUNNING",
            "retryCount": 0,
            "retriedRelationships": [],
            "backoffMechanism": "PENALIZE_FLOWFILE",
            "maxBackoffPeriod": "10 mins",
            "componentType": "PROCESSOR",
            "groupIdentifier": group_id,
        })

    def endpoint(node_id: str) -> dict:
        ident = component_id(flow_id, "processor", node_id)
        return {"id": ident, "instanceIdentifier": ident, "type": "PROCESSOR", "groupId": group_id}

    wired = []
    for edge in connections:
        edge_id = component_id(flow_id, "connection", edge["id"])
        wired.append({
            "identifier": edge_id,
            "instanceIdentifier": edge_id,
            "name": edge["id"],
            "source": endpoint(edge["source"]),
            "destination": endpoint(edge["target"]),
            "selectedRelationships": ["success"],
            "labelIndex": 1,
            "zIndex": 0,
            "backPressureObjectThreshold": 100,
            "backPressureDataSizeThreshold": "1 MB",
            "flowFileExpiration": "0 sec",
            "prioritizers": [],
            "bends": [],
            "loadBalanceStrategy": "DO_NOT_LOAD_BALANCE",
            "loadBalanceCompression": "DO_NOT_COMPRESS",
            "componentType": "CONNECTION",
            "groupIdentifier": group_id,
        })

    return json.dumps({
        "encodingVersion": {"majorVersion": 2, "minorVersion": 0},
        "maxTimerDrivenThreadCount": 1,
        "registries": [],
        "parameterContexts": [],
        "parameterProviders": [],
        "controllerServices": [],
        "reportingTasks": [],
        "templates": [],
        "rootGroup": {
            "identifier": group_id,
            "instanceIdentifier": group_id,
            "name": definition["name"],
            "comments": definition.get("description") or "",
            "position": {"x": 0.0, "y": 0.0},
            "processGroups": [],
            "remoteProcessGroups": [],
            "processors": processors,
            "inputPorts": [],
            "outputPorts": [],
            "connections": wired,
            "labels": [],
            "funnels": [],
            "controllerServices": [],
            "variables": {},
            "defaultFlowFileExpiration": "0 sec",
            "defaultBackPressureObjectThreshold": 100,
            "defaultBackPressureDataSizeThreshold": "1 MB",
            "componentType": "PROCESS_GROUP",
            "flowFileConcurrency": "UNBOUNDED",
            "flowFileOutboundPolicy": "STREAM_WHEN_AVAILABLE",
        },
    }, sort_keys=True, separators=(",", ":"))
