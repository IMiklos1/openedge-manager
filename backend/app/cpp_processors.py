"""Processor contract for the verified subset of MiNiFi C++ 1.1.0."""

from .processor_properties import ATTRIBUTE_NAME, SCHEDULING_FIELDS, checked_value, resolve_fields
from .runtimes import CPP, VERSIONS

BUNDLE = {"group": "org.apache.nifi.minifi", "artifact": "minifi-standard-processors", "version": VERSIONS[CPP]}

CPP_PROCESSORS = {
    "GenerateFlowFile": {
        "description": "Generate synthetic FlowFiles.",
        "inputRequirement": "INPUT_FORBIDDEN",
        "relationships": {"success": {}},
        "properties": {
            "File Size": {"type": "size", "default": "1 KB", "max": 65536},
            "Batch Size": {"type": "integer", "default": 1, "min": 1, "max": 20},
            "Data Format": {"type": "choice", "default": "Binary", "choices": ["Binary", "Text"]},
            "Unique FlowFiles": {"type": "boolean", "default": True},
            "Custom Text": {"type": "text", "multiline": True, "max": 4096},
        },
    },
    "UpdateAttribute": {
        "description": "Set literal FlowFile attributes using dynamic properties.",
        "inputRequirement": "INPUT_REQUIRED",
        "relationships": {"success": {}, "failure": {}},
        "properties": {},
        "dynamic_properties": True,
    },
    "LogAttribute": {
        "description": "Log FlowFile attributes and optional content.",
        "inputRequirement": "INPUT_REQUIRED",
        "relationships": {"success": {}},
        "properties": {
            "Log Level": {"type": "choice", "default": "info", "choices": ["trace", "debug", "info", "warn", "error", "critical"]},
            "Attributes to Log": {"type": "text", "max": 512},
            "Attributes to Ignore": {"type": "text", "max": 512},
            "Log Payload": {"type": "boolean", "default": False},
            "Hexencode Payload": {"type": "boolean", "default": False},
            "Maximum Payload Line Length": {"type": "integer", "default": 0, "min": 0, "max": 4096},
            "Log Prefix": {"type": "text", "max": 120},
            "FlowFiles To Log": {"type": "integer", "default": 1, "min": 1, "max": 20},
        },
    },
}

for name, processor in CPP_PROCESSORS.items():
    processor.update(
        type=f"org.apache.nifi.minifi.processors.{name}",
        bundle=BUNDLE,
        tags=["cpp"],
        scheduling={key: SCHEDULING_FIELDS[key] for key in ("period", "tasks", "penalty", "yield")}
        | {"period": SCHEDULING_FIELDS["period"] | {"default": "5 sec" if name == "GenerateFlowFile" else "1 sec"}},
    )
    processor.setdefault("dynamic_properties", False)


def resolve_cpp_processor(node, errors):
    scope = f"Node {node['id']}"
    schema = CPP_PROCESSORS[node["type"]]
    properties = resolve_fields(node.get("config", {}), schema["properties"], scope, errors)
    schedule = resolve_fields(node.get("scheduling", {}), schema["scheduling"], scope, errors)
    attributes = node.get("attributes", {})
    if attributes and not schema["dynamic_properties"]:
        errors.append(f"{scope}: this processor has no dynamic properties.")
    for key, value in attributes.items():
        if not ATTRIBUTE_NAME.fullmatch(key):
            errors.append(f"{scope}, {key}: enter a valid FlowFile attribute name.")
            continue
        try:
            properties[key] = checked_value(value, {"type": "text", "max": 256})
        except ValueError as exc:
            errors.append(f"{scope}, {key}: {exc}")
    if "Custom Text" in properties and (properties["Data Format"] != "Text" or properties["Unique FlowFiles"]):
        errors.append(f"{scope}, Custom Text: choose Text and turn off Unique FlowFiles.")
    return {
        key: str(value).lower() if isinstance(value, bool) else str(value)
        for key, value in properties.items()
    }, schedule, set(schema["relationships"])
