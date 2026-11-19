import json
from uuid import NAMESPACE_URL, uuid5

from .catalog import CATALOG
from .processor_properties import PROCESSORS, QUEUE_FIELDS, resolve_fields, resolve_processor

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
NODE_FIELDS = {"id", "type", "label", "description", "position", "config", "scheduling", "attributes", "auto_terminate_success"}


def component_id(flow_id: str, *parts: str) -> str:
    return str(uuid5(NAMESPACE_URL, json.dumps(["openedge-manager", flow_id, *parts])))


def runtime_validation(definition: dict):
    errors = validate_flow(definition)
    nodes = definition.get("nodes", [])
    connections = definition.get("connections", [])
    if not nodes or len(nodes) > 20 or len(connections) > 40:
        errors.append("Use 1–20 processors and at most 40 connections.")
    if definition.get("parameters"):
        errors.append("Flow parameters are not available in this runtime profile.")

    configurations = {}
    for node in nodes:
        for field in sorted(node.keys() - NODE_FIELDS):
            errors.append(f"Node {node['id']}, {field}: unknown processor field.")
        if node["type"] not in PROCESSORS:
            errors.append(f"Node {node['id']}: {node['type']} is unavailable in this runtime profile.")
            continue
        configurations[node["id"]] = resolve_processor(node, errors)

    kinds = {node["id"]: node["type"] for node in nodes}
    sinks = {edge["target"] for edge in connections}
    connected = {edge["source"] for edge in connections}
    if "GenerateFlowFile" not in kinds.values():
        errors.append("Add at least one GenerateFlowFile processor.")
    if configurations and not any(settings["state"] == "RUNNING" for _, settings in configurations.values()):
        errors.append("Keep at least one processor enabled for C2 application confirmation.")
    if len({edge["id"] for edge in connections}) != len(connections):
        errors.append("Connection IDs must be unique.")
    for node in nodes:
        node_id = node["id"]
        if node["type"] == "LogAttribute" and node_id not in sinks:
            errors.append(f"Node {node_id}: LogAttribute needs an incoming connection.")
        termination = node.get("auto_terminate_success")
        if termination is not None and termination == (node_id in connected):
            errors.append(f"Node {node_id}: terminate success only when it has no outgoing connection.")

    queues = {}
    for edge in connections:
        if (kinds.get(edge["source"]), kinds.get(edge["target"]), edge["source_relationship"]) != (
            "GenerateFlowFile", "LogAttribute", "success",
        ):
            errors.append(f"Connection {edge['id']}: use GenerateFlowFile → LogAttribute over success.")
        queues[edge["id"]] = resolve_fields(edge.get("queue", {}), QUEUE_FIELDS, f"Connection {edge['id']}", errors)
    return errors, configurations, queues


def compile_minifi_java_json(definition: dict) -> str:
    errors, configurations, queues = runtime_validation(definition)
    if errors:
        raise CompileError("; ".join(errors))
    nodes = definition["nodes"]
    connections = definition["connections"]
    flow_id = definition["flow_id"]
    group_id = component_id(flow_id, "root")
    connected = {edge["source"] for edge in connections}
    processors = []
    for index, node in enumerate(nodes):
        kind = node["type"]
        processor_id = component_id(flow_id, "processor", node["id"])
        properties, schedule = configurations[node["id"]]
        processors.append({
            "identifier": processor_id,
            "instanceIdentifier": processor_id,
            "name": node.get("label") or kind,
            "comments": node.get("description") or "",
            "position": node.get("position") or {"x": float(index * 300), "y": 0.0},
            "type": f"org.apache.nifi.processors.standard.{kind}",
            "bundle": {"group": "org.apache.nifi.minifi", "artifact": "minifi-standard-nar", "version": MINIFI_VERSION},
            "properties": properties,
            "propertyDescriptors": {},
            "style": {},
            "schedulingPeriod": schedule["period"],
            "schedulingStrategy": "TIMER_DRIVEN",
            "executionNode": "ALL",
            "penaltyDuration": schedule["penalty"],
            "yieldDuration": schedule["yield"],
            "bulletinLevel": schedule["bulletin_level"],
            "runDurationMillis": schedule["run_duration_ms"],
            "concurrentlySchedulableTaskCount": schedule["tasks"],
            "autoTerminatedRelationships": [] if node["id"] in connected else ["success"],
            "scheduledState": schedule["state"],
            "retryCount": schedule["retry_count"],
            "retriedRelationships": ["success"] if schedule["retry_success"] else [],
            "backoffMechanism": schedule["backoff"],
            "maxBackoffPeriod": schedule["max_backoff"],
            "componentType": "PROCESSOR",
            "groupIdentifier": group_id,
        })

    def endpoint(node_id: str) -> dict:
        ident = component_id(flow_id, "processor", node_id)
        return {"id": ident, "instanceIdentifier": ident, "type": "PROCESSOR", "groupId": group_id}

    wired = []
    for edge in connections:
        edge_id = component_id(flow_id, "connection", edge["id"])
        queue = queues[edge["id"]]
        wired.append({
            "identifier": edge_id,
            "instanceIdentifier": edge_id,
            "name": edge.get("label") or edge["id"],
            "source": endpoint(edge["source"]),
            "destination": endpoint(edge["target"]),
            "selectedRelationships": ["success"],
            "labelIndex": 1,
            "zIndex": 0,
            "backPressureObjectThreshold": queue["object_threshold"],
            "backPressureDataSizeThreshold": queue["data_size_threshold"],
            "flowFileExpiration": queue["expiration"],
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
