"""Configuration contract for the pinned Apache MiNiFi C++ release."""

import json
from pathlib import Path

from .processor_properties import SCHEDULING_FIELDS, component_properties, property_text, resolve_fields, resolve_properties
from .runtimes import CPP, VERSIONS


_catalog = json.loads(Path(__file__).with_name("minifi_cpp_catalog.json").read_text(encoding="utf-8"))
if _catalog["runtime_version"] != VERSIONS[CPP]:
    raise ValueError("The MiNiFi C++ catalog does not match the supported runtime")

# Preserve the defaults and limits of existing OEM-authored C++ flows.
LEGACY_PROPERTIES = {
    "GenerateFlowFile": {
        "File Size": {"type": "size", "default": "1 KB", "max": 65536},
        "Batch Size": {"type": "integer", "default": 1, "min": 1, "max": 20},
        "Data Format": {"type": "choice", "default": "Binary", "choices": ["Binary", "Text"]},
        "Unique FlowFiles": {"type": "boolean", "default": True},
        "Custom Text": {"type": "text", "multiline": True, "max": 4096},
    },
    "LogAttribute": {
        "Log Level": {"type": "choice", "default": "info", "choices": ["trace", "debug", "info", "warn", "error", "critical"]},
        "Attributes to Log": {"type": "text", "max": 512},
        "Attributes to Ignore": {"type": "text", "max": 512},
        "Log Payload": {"type": "boolean", "default": False},
        "Hexencode Payload": {"type": "boolean", "default": False},
        "Maximum Payload Line Length": {"type": "integer", "default": 0, "min": 0, "max": 4096},
        "Log Prefix": {"type": "text", "max": 120},
        "FlowFiles To Log": {"type": "integer", "default": 1, "min": 1, "max": 20},
    },
}

# The native manifest reports dynamic support without an Expression Language scope.
DYNAMIC_EXPRESSIONS = {"RouteOnAttribute", "RouteText", "UpdateAttribute"}


def cpp_schema(name, component):
    properties = component_properties(component)
    for key, overrides in LEGACY_PROPERTIES.get(name, {}).items():
        properties[key].update(overrides, legacy=True, multiline=overrides.get("multiline", False), expression_scope="NONE")
    schema = component | {
        "properties": properties,
        "dynamic_properties": component["dynamic"],
        "dynamic": [{
            "name": "Dynamic property",
            "description": "Values support FlowFile Attribute Expression Language.",
            "expressionLanguageScope": "FLOWFILE_ATTRIBUTES",
        }] if name in DYNAMIC_EXPRESSIONS else [],
        "tags": ["cpp", *component["platforms"], component["bundle"]["artifact"]],
    }
    if "relationships" in component:
        if name == "RouteText":
            schema["dynamicRelationshipStrategy"] = {"dynamicValue": "Dynamic Routing", "property": "Routing Strategy"}
        schedule = {key: SCHEDULING_FIELDS[key] for key in ("period", "tasks", "penalty", "yield")}
        schedule["period"] = schedule["period"] | {"default": "5 sec" if name == "GenerateFlowFile" else "1 sec"}
        if component["triggerSerially"]:
            schedule["tasks"] = schedule["tasks"] | {"max": 1}
        schema["scheduling"] = schedule
    return schema


CPP_PROCESSORS = {name: cpp_schema(name, component) for name, component in _catalog["processors"].items()}
CPP_SERVICES = {name: cpp_schema(name, component) for name, component in _catalog["services"].items()}
CPP_COMPONENTS_BY_TYPE = {schema["type"]: schema for schema in (*CPP_PROCESSORS.values(), *CPP_SERVICES.values())}


def resolve_cpp_processor(node, services, errors):
    scope = f"Node {node['id']}"
    kind = node["type"]
    schema = CPP_PROCESSORS[kind]
    defaults = {key: property_text(field["default"]) for key, field in LEGACY_PROPERTIES.get(kind, {}).items()
                if "default" in field}
    properties, effective = resolve_properties(node, schema, services, scope, errors, defaults=defaults)
    schedule = resolve_fields(node.get("scheduling", {}), schema["scheduling"], scope, errors)
    relationships = set(schema["relationships"])
    if schema["dynamicRelationship"]:
        strategy = schema.get("dynamicRelationshipStrategy")
        if not strategy or effective.get(strategy["property"]) == strategy["dynamicValue"]:
            relationships.update(node.get("attributes", {}))
    if kind == "ExecuteScript" and bool(effective.get("Script Body")) == bool(effective.get("Script File")):
        errors.append(f"{scope}: configure exactly one of Script File or Script Body.")
    return properties, schedule, relationships
