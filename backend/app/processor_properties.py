"""Configuration contract for the processors shipped and tested with MiNiFi Java 2.12.0."""

import re


CHARSETS = ["UTF-8", "US-ASCII", "ISO-8859-1", "UTF-16", "UTF-16BE", "UTF-16LE"]
ATTRIBUTE_NAME = re.compile(r"[A-Za-z_][\w.-]{0,63}", re.ASCII)
DURATION = re.compile(r"(\d{1,8}) *(ms|sec|min|hour)")
SIZE = re.compile(r"(\d{1,8}) *(B|KB|MB)")
SAFE_ATTRIBUTE_REGEX = re.compile(r"\^?[\w.-]+(?:\|[\w.-]+)*\$?", re.ASCII)


PROCESSORS = {
    "GenerateFlowFile": {
        "description": "Generate test data on the edge.",
        "dynamic_properties": True,
        "properties": {
            "File Size": {"type": "size", "default": "1 B", "max": 65536},
            "Batch Size": {"type": "integer", "default": 1, "min": 1, "max": 20},
            "Data Format": {"type": "choice", "default": "Binary", "choices": ["Binary", "Text"]},
            "Unique FlowFiles": {"type": "boolean", "default": False},
            "Custom Text": {"type": "text", "multiline": True, "max": 4096},
            "Character Set": {"type": "choice", "default": "UTF-8", "choices": CHARSETS},
            "Mime Type": {"type": "text", "max": 120},
        },
    },
    "LogAttribute": {
        "description": "Log received FlowFile attributes.",
        "dynamic_properties": False,
        "properties": {
            "Log Level": {"type": "choice", "default": "info", "choices": ["trace", "debug", "info", "warn", "error"]},
            "Attributes to Log": {"type": "text", "max": 512},
            "Attributes to Ignore": {"type": "text", "max": 512},
            "Attributes to Log Regular Expression": {"type": "attribute_regex", "default": ".*"},
            "Attributes to Ignore Regular Expression": {"type": "attribute_regex"},
            "Output Format": {"type": "choice", "default": "Line per Attribute", "choices": ["Line per Attribute", "Single Line"]},
            "Log Payload": {"type": "boolean", "default": False},
            "Log FlowFile Properties": {"type": "boolean", "default": True},
            "Log Prefix": {"type": "text", "max": 120},
            "Character Set": {"type": "choice", "default": "UTF-8", "choices": CHARSETS},
        },
    },
}

SCHEDULING_FIELDS = {
    "period": {"type": "duration", "min": 250, "max": 86400000, "label": "Run schedule"},
    "tasks": {"type": "integer", "min": 1, "max": 4, "default": 1, "label": "Concurrent tasks"},
    "penalty": {"type": "duration", "min": 0, "max": 86400000, "default": "30 sec", "label": "Penalty duration"},
    "yield": {"type": "duration", "min": 0, "max": 86400000, "default": "1 sec", "label": "Yield duration"},
    "run_duration_ms": {"type": "integer", "min": 0, "max": 1000, "default": 0, "label": "Run duration (ms)"},
    "bulletin_level": {"type": "choice", "choices": ["DEBUG", "INFO", "WARN", "ERROR", "NONE"], "default": "WARN", "label": "Bulletin level"},
    "state": {"type": "choice", "choices": ["RUNNING", "DISABLED"], "default": "RUNNING", "label": "Initial state"},
    "retry_count": {"type": "integer", "min": 0, "max": 10, "default": 0, "label": "Retry count"},
    "retry_success": {"type": "boolean", "default": False, "label": "Retry success"},
    "backoff": {"type": "choice", "choices": ["PENALIZE_FLOWFILE", "YIELD_PROCESSOR"], "default": "PENALIZE_FLOWFILE", "label": "Retry backoff"},
    "max_backoff": {"type": "duration", "min": 1000, "max": 86400000, "default": "10 min", "label": "Maximum backoff"},
}

QUEUE_FIELDS = {
    "object_threshold": {"type": "integer", "min": 1, "max": 10000, "default": 100, "label": "Back pressure objects"},
    "data_size_threshold": {"type": "size", "min": 1, "max": 104857600, "default": "1 MB", "label": "Back pressure data size"},
    "expiration": {"type": "duration", "min": 0, "max": 86400000, "default": "0 sec", "label": "FlowFile expiration"},
}


def processor_schema(kind: str) -> dict:
    return PROCESSORS[kind] | {
        "scheduling": SCHEDULING_FIELDS | {
            "period": SCHEDULING_FIELDS["period"] | {"default": "5 sec" if kind == "GenerateFlowFile" else "1 sec"},
        },
    }


def checked_value(value, field):
    kind = field["type"]
    if kind == "boolean":
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value in {"true", "false"}:
            return value == "true"
        raise ValueError("Use true or false.")
    if kind == "integer":
        if isinstance(value, str) and re.fullmatch(r"[0-9]{1,9}", value):
            value = int(value)
        if type(value) is int and field["min"] <= value <= field["max"]:
            return value
        raise ValueError(f"Use an integer from {field['min']} to {field['max']}.")
    if not isinstance(value, str) or not value.strip() or "\x00" in value or "${" in value or "#{" in value:
        raise ValueError("Use a non-empty literal value. Expressions and parameter references are unavailable.")
    if kind == "choice":
        if value in field["choices"]:
            return value
        raise ValueError(f"Choose one of: {', '.join(field['choices'])}.")
    if kind in {"size", "duration"}:
        units = {"B": 1, "KB": 1024, "MB": 1048576} if kind == "size" else {"ms": 1, "sec": 1000, "min": 60000, "hour": 3600000}
        match = (SIZE if kind == "size" else DURATION).fullmatch(value)
        if match:
            magnitude = int(match[1]) * units[match[2]]
            if field.get("min", 0) <= magnitude <= field["max"]:
                return f"{int(match[1])} {match[2]}"
        raise ValueError(f"Use {', '.join(units)} within {field.get('min', 0)}–{field['max']} {next(iter(units))}.")
    if kind == "attribute_regex":
        if len(value) <= 120 and (value == ".*" or SAFE_ATTRIBUTE_REGEX.fullmatch(value)):
            return value
        raise ValueError("Use .* or a list of literal attribute names separated by |.")
    if len(value) > field["max"] or (not field.get("multiline") and ("\n" in value or "\r" in value)):
        raise ValueError(f"Use at most {field['max']} characters in the supported text format.")
    return value


def resolve_fields(values, fields, scope, errors):
    result = {name: field["default"] for name, field in fields.items() if "default" in field}
    for name, value in values.items():
        if name not in fields:
            errors.append(f"{scope}, {name}: unknown field.")
            continue
        try:
            result[name] = checked_value(value, fields[name])
        except ValueError as exc:
            errors.append(f"{scope}, {name}: {exc}")
    return result


def resolve_processor(node, errors):
    scope = f"Node {node['id']}"
    schema = processor_schema(node["type"])
    props = resolve_fields(node.get("config", {}), schema["properties"], scope, errors)
    scheduling = resolve_fields(node.get("scheduling", {}), schema["scheduling"], scope, errors)
    dynamic = node.get("attributes", {})
    if dynamic and not schema["dynamic_properties"]:
        errors.append(f"{scope}: this processor has no dynamic attributes.")
    for key, value in dynamic.items():
        if not ATTRIBUTE_NAME.fullmatch(key) or key in schema["properties"]:
            errors.append(f"{scope}, {key}: enter a distinct attribute name.")
        else:
            try:
                props[key] = checked_value(value, {"type": "text", "max": 256})
            except ValueError as exc:
                errors.append(f"{scope}, {key}: {exc}")
    if "Custom Text" in props and (props.get("Data Format") != "Text" or props.get("Unique FlowFiles")):
        errors.append(f"{scope}, Custom Text: choose Text and turn off Unique FlowFiles.")
    if scheduling["retry_success"] and scheduling["retry_count"] == 0:
        errors.append(f"{scope}: Retry success requires a positive retry count.")
    return {key: str(value).lower() if isinstance(value, bool) else str(value) for key, value in props.items()}, scheduling
