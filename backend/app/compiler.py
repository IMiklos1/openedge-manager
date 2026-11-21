import json
from collections import Counter, defaultdict
from graphlib import CycleError, TopologicalSorter
from uuid import NAMESPACE_URL, uuid5

from .catalog import CONTROLLER_SERVICES, PROCESSORS
from .cpp_processors import CPP_PROCESSORS, resolve_cpp_processor
from .runtimes import CPP, JAVA
from .processor_properties import (
    QUEUE_FIELDS, SERVICE_SCHEMAS, resolve_fields, resolve_processor, resolve_properties,
)

NODE_FIELDS = {"id", "type", "label", "description", "position", "config", "scheduling",
               "attributes", "auto_terminate_success", "auto_terminate", "retry_relationships"}


class CompileError(ValueError):
    pass


def component_id(flow_id: str, *parts: str) -> str:
    return str(uuid5(NAMESPACE_URL, json.dumps(["openedge-manager", flow_id, *parts])))


def configured_services(items, errors):
    if len(items) > 100:
        errors.append("Use at most 100 controller services.")
    types = {item["id"]: item["type"] for item in items}
    if len(types) != len(items):
        errors.append("Controller service IDs must be unique.")
    interfaces = {
        key: {api["className"] for api in CONTROLLER_SERVICES.get(kind, {}).get("apis", [])}
        for key, kind in types.items()
    }
    configurations = {}
    for item in items:
        scope = f"Controller service {item['id']}"
        if (schema := SERVICE_SCHEMAS.get(item["type"])) is None:
            errors.append(f"{scope}: {item['type']} is unavailable in the pinned image.")
            continue
        properties, _ = resolve_properties(item, schema, interfaces, scope, errors)
        configurations[item["id"]] = properties
    try:
        graph = {
            key: [value for name, value in values.items()
                  if SERVICE_SCHEMAS.get(types[key], {}).get("properties", {}).get(name, {}).get("service") and value]
            for key, values in configurations.items()
        }
        list(TopologicalSorter(graph).static_order())
    except CycleError:
        errors.append("Controller services must not have circular references.")
    return interfaces, configurations


def runtime_validation(definition: dict):
    errors = []
    nodes = definition.get("nodes", [])
    connections = definition.get("connections", [])
    if not nodes or len(nodes) > 100 or len(connections) > 300:
        errors.append("Use 1–100 processors and at most 300 connections.")
    if definition.get("parameters"):
        errors.append("Flow parameter contexts are unavailable.")

    kinds = {node["id"]: node["type"] for node in nodes}
    if len(kinds) != len(nodes):
        errors.append("Node IDs must be unique.")
    if len({edge["id"] for edge in connections}) != len(connections):
        errors.append("Connection IDs must be unique.")

    cpp = definition.get("runtime", JAVA) == CPP
    catalog = CPP_PROCESSORS if cpp else PROCESSORS
    services = definition.get("controller_services", [])
    if cpp:
        interfaces, service_config = {}, {}
        if services:
            errors.append("Controller services are unavailable in the C++ editor profile.")
    else:
        interfaces, service_config = configured_services(services, errors)
    configurations = {}
    for node in nodes:
        for field in sorted(node.keys() - NODE_FIELDS):
            errors.append(f"Node {node['id']}, {field}: unknown processor field.")
        if node["type"] not in catalog:
            errors.append(f"Node {node['id']}: {node['type']} is unavailable in the pinned image.")
            continue
        configurations[node["id"]] = (
            resolve_cpp_processor(node, errors) if cpp else resolve_processor(node, interfaces, errors)
        )
    if configurations and not any(schedule.get("state", "RUNNING") == "RUNNING" for _, schedule, _ in configurations.values()):
        errors.append("Keep at least one processor enabled for C2 application confirmation.")

    incoming = Counter(edge["target"] for edge in connections)
    routed = defaultdict(set)
    queues = {}
    for edge in connections:
        source, target = edge["source"], edge["target"]
        relationship = edge.get("source_relationship", "success")
        scope = f"Connection {edge['id']}"
        if source not in kinds or target not in kinds:
            errors.append(f"{scope}: source and destination must reference existing processors.")
        if source in configurations and relationship not in configurations[source][2]:
            errors.append(f"{scope}: {relationship!r} is not available on the source processor.")
        routed[source].add(relationship)
        queues[edge["id"]] = resolve_fields(edge.get("queue", {}), QUEUE_FIELDS, scope, errors)

    relationship_settings = {}
    for node in nodes:
        node_id = node["id"]
        if node["type"] not in catalog or node_id not in configurations:
            continue
        _, schedule, available = configurations[node_id]
        requirement = catalog[node["type"]].get("inputRequirement")
        scope = f"Node {node_id}"
        if requirement == "INPUT_REQUIRED" and not incoming[node_id]:
            errors.append(f"{scope}: this processor needs an incoming connection.")
        if requirement == "INPUT_FORBIDDEN" and incoming[node_id] > 0:
            errors.append(f"{scope}: this processor does not accept incoming connections.")
        connected = routed[node_id]
        configured = node.get("auto_terminate")
        if configured is None:
            terminated = available - connected
            legacy = node.get("auto_terminate_success")
            if legacy is not None and "success" in available and legacy != ("success" in terminated):
                errors.append(f"{scope}: terminate success only when it has no outgoing connection.")
        else:
            terminated = set(configured)
            if terminated & connected:
                errors.append(f"{scope}: a relationship cannot be connected and terminated.")
            if invalid := terminated - available:
                errors.append(f"{scope}: unknown terminated relationships: {', '.join(sorted(invalid))}.")
            if missing := available - connected - terminated:
                errors.append(f"{scope}: connect or terminate {', '.join(sorted(missing))}.")
        retry = set(node.get("retry_relationships", []))
        if schedule.get("retry_success"):
            retry.add("success")
        if retry and cpp:
            errors.append(f"{scope}: relationship retry is unavailable in the C++ editor profile.")
        elif retry and not schedule["retry_count"]:
            errors.append(f"{scope}: retry requires a positive retry count.")
        if invalid := retry - available:
            errors.append(f"{scope}: unknown retry relationships: {', '.join(sorted(invalid))}.")
        relationship_settings[node_id] = (sorted(terminated), sorted(retry))
    return errors, configurations, queues, service_config, relationship_settings


def versioned_properties(flow_id, component, values):
    # Internal service references use the same deterministic identity as the controller service.
    props, descriptors = {}, {}
    for key, value in values.items():
        field = component["properties"].get(key, {})
        service_reference = bool(field.get("service"))
        if service_reference and value:
            value = component_id(flow_id, "service", value)
        props[key] = value
        descriptors[key] = {
            "name": key, "displayName": field.get("displayName", key), "dynamic": key not in component["properties"],
            "sensitive": False, "identifiesControllerService": service_reference,
        }
    return {"properties": props, "propertyDescriptors": descriptors}


def compile_flow(definition: dict) -> str:
    if definition.get("runtime", JAVA) == CPP:
        return compile_minifi_cpp_json(definition)
    return compile_minifi_java_json(definition)


def compile_minifi_cpp_json(definition: dict) -> str:
    errors, configurations, queues, _, relationships = runtime_validation(definition)
    if errors:
        raise CompileError("; ".join(errors))
    flow_id = definition["flow_id"]
    processors = []
    for node in definition["nodes"]:
        node_id, kind = node["id"], node["type"]
        properties, schedule, _ = configurations[node_id]
        processors.append({
            "identifier": component_id(flow_id, "processor", node_id),
            "name": node.get("label") or kind,
            "type": CPP_PROCESSORS[kind]["type"],
            "bundle": CPP_PROCESSORS[kind]["bundle"],
            "properties": properties,
            "schedulingStrategy": "TIMER_DRIVEN",
            "schedulingPeriod": schedule["period"],
            "concurrentlySchedulableTaskCount": schedule["tasks"],
            "penaltyDuration": schedule["penalty"],
            "yieldDuration": schedule["yield"],
            "autoTerminatedRelationships": relationships[node_id][0],
        })

    connections = []
    for edge in definition["connections"]:
        queue = queues[edge["id"]]
        connections.append({
            "identifier": component_id(flow_id, "connection", edge["id"]),
            "name": edge.get("label") or edge["id"],
            "source": {"id": component_id(flow_id, "processor", edge["source"])},
            "destination": {"id": component_id(flow_id, "processor", edge["target"])},
            "selectedRelationships": [edge.get("source_relationship", "success")],
            "backPressureObjectThreshold": queue["object_threshold"],
            "backPressureDataSizeThreshold": queue["data_size_threshold"],
            "flowFileExpiration": queue["expiration"],
        })

    return json.dumps({"rootGroup": {
        "identifier": component_id(flow_id, "root"),
        "name": definition["name"],
        "processors": processors,
        "connections": connections,
    }}, sort_keys=True, separators=(",", ":"))


def compile_minifi_java_json(definition: dict) -> str:
    errors, configurations, queues, service_config, relationship_settings = runtime_validation(definition)
    if errors:
        raise CompileError("; ".join(errors))
    nodes = definition["nodes"]
    flow_id = definition["flow_id"]
    group_id = component_id(flow_id, "root")
    processors = []
    for index, node in enumerate(nodes):
        kind = node["type"]
        processor_id = component_id(flow_id, "processor", node["id"])
        properties, schedule, _ = configurations[node["id"]]
        terminated, retry = relationship_settings[node["id"]]
        processors.append({
            "identifier": processor_id,
            "instanceIdentifier": processor_id,
            "name": node.get("label") or kind,
            "comments": node.get("description") or "",
            "position": node.get("position") or {"x": float(index * 300), "y": 0.0},
            "type": PROCESSORS[kind]["type"],
            "bundle": PROCESSORS[kind]["bundle"],
            **versioned_properties(flow_id, PROCESSORS[kind], properties),
            "style": {},
            "schedulingPeriod": schedule["period"],
            "schedulingStrategy": "TIMER_DRIVEN",
            "executionNode": "ALL",
            "penaltyDuration": schedule["penalty"],
            "yieldDuration": schedule["yield"],
            "bulletinLevel": schedule["bulletin_level"],
            "runDurationMillis": schedule["run_duration_ms"],
            "concurrentlySchedulableTaskCount": schedule["tasks"],
            "autoTerminatedRelationships": terminated,
            "scheduledState": schedule["state"],
            "retryCount": schedule["retry_count"],
            "retriedRelationships": retry,
            "backoffMechanism": schedule["backoff"],
            "maxBackoffPeriod": schedule["max_backoff"],
            "componentType": "PROCESSOR",
            "groupIdentifier": group_id,
        })

    services = []
    for item in definition.get("controller_services", []):
        component = CONTROLLER_SERVICES[item["type"]]
        identifier = component_id(flow_id, "service", item["id"])
        services.append({
            "identifier": identifier,
            "instanceIdentifier": identifier,
            "name": item.get("label") or item["type"],
            "comments": item.get("description") or "",
            "type": component["type"],
            "bundle": component["bundle"],
            "controllerServiceApis": component["apis"],
            "scheduledState": item.get("state", "ENABLED"),
            "bulletinLevel": "WARN",
            "componentType": "CONTROLLER_SERVICE",
            "groupIdentifier": group_id,
            **versioned_properties(flow_id, component, service_config[item["id"]]),
        })

    def endpoint(node_id: str) -> dict:
        ident = component_id(flow_id, "processor", node_id)
        return {"id": ident, "instanceIdentifier": ident, "type": "PROCESSOR", "groupId": group_id}

    wired = []
    for edge in definition["connections"]:
        edge_id = component_id(flow_id, "connection", edge["id"])
        queue = queues[edge["id"]]
        wired.append({
            "identifier": edge_id,
            "instanceIdentifier": edge_id,
            "name": edge.get("label") or edge["id"],
            "source": endpoint(edge["source"]),
            "destination": endpoint(edge["target"]),
            "selectedRelationships": [edge.get("source_relationship", "success")],
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
        "maxTimerDrivenThreadCount": max(p["concurrentlySchedulableTaskCount"] for p in processors),
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
            "controllerServices": services,
            "variables": {},
            "defaultFlowFileExpiration": "0 sec",
            "defaultBackPressureObjectThreshold": 100,
            "defaultBackPressureDataSizeThreshold": "1 MB",
            "componentType": "PROCESS_GROUP",
            "flowFileConcurrency": "UNBOUNDED",
            "flowFileOutboundPolicy": "STREAM_WHEN_AVAILABLE",
        },
    }, sort_keys=True, separators=(",", ":"))
