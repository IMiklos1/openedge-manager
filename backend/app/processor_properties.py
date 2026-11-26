"""Configuration contract for the processors shipped and tested with MiNiFi Java 2.12.0."""

import math
import re

from .catalog import CONTROLLER_SERVICES, PROCESSORS


CHARSETS = ["UTF-8", "US-ASCII", "ISO-8859-1", "UTF-16", "UTF-16BE", "UTF-16LE"]
ATTRIBUTE_NAME = re.compile(r"[A-Za-z_][\w.-]{0,63}", re.ASCII)
DURATION = re.compile(r"(\d{1,8}) *(ms|sec|min|hour)")
SIZE = re.compile(r"(\d{1,8}) *(B|KB|MB)")
SAFE_ATTRIBUTE_REGEX = re.compile(r"\^?[\w.-]+(?:\|[\w.-]+)*\$?", re.ASCII)
NATIVE_INTEGER_FORMATS = {
    "INTEGER_VALIDATOR": (r"-?[0-9]{1,19}", -(2**63), 2**63 - 1),
    "NON_NEGATIVE_INTEGER_VALIDATOR": (r"[0-9]{1,20}", 0, 2**64 - 1),
    "PORT_VALIDATOR": (r"[0-9]{1,5}", 0, 65535),
}


LEGACY_PROPERTIES = {
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


def component_properties(component):
    result = {}
    for key, descriptor in component["properties"].items():
        choices = descriptor.get("choices", [])
        if descriptor.get("validator") == "BOOLEAN_VALIDATOR" and not choices:
            choices = [{"value": value, "displayName": value} for value in ("true", "false")]
        options = [choice["value"] for choice in choices]
        default = descriptor.get("defaultValue")
        field = {
            "type": "choice" if options else "text",
            "label": descriptor.get("displayName", key),
            "description": descriptor.get("description"),
            "required": descriptor.get("required", False),
            "sensitive": descriptor.get("sensitive", False),
            "expression_scope": descriptor.get("expressionLanguageScope", "NONE"),
            "dependencies": descriptor.get("dependencies", {}),
        }
        if options:
            field.update(choices=options, choice_labels={item["value"]: item["displayName"] for item in choices})
        if set(value.lower() for value in options) == {"true", "false"}:
            field["type"] = "boolean"
        if field["type"] == "text":
            field.update(multiline=True, max=32768)
        if default is not None and not field["sensitive"]:
            field["default"] = default
        if service := descriptor.get("service"):
            field.update(type="service", service=service)
        if descriptor.get("dynamicallyModifiesClasspath"):
            field["modifies_classpath"] = True
        for name in ("validator", "platforms"):
            if name in descriptor:
                field[name] = descriptor[name]
        result[key] = field
    return result


def component_schema(kind, component, processor=False):
    properties = component_properties(component)
    if legacy := LEGACY_PROPERTIES.get(kind):
        for name, field in legacy["properties"].items():
            properties[name].update(field, legacy=True, multiline=field.get("multiline", False), expression_scope="NONE")
    schema = component | {
        "properties": properties, "dynamic_properties": bool(component.get("dynamic")),
    }
    if processor:
        schedule = component.get("defaultSchedule", {})
        tasks = SCHEDULING_FIELDS["tasks"] | {"default": int(schedule.get("concurrentTasks", 1))}
        if component.get("triggerSerially"):
            tasks["max"] = 1
        schema["scheduling"] = SCHEDULING_FIELDS | {
            "period": SCHEDULING_FIELDS["period"] | {
                "default": "5 sec" if kind == "GenerateFlowFile" else schedule.get("period", "1 sec"),
            },
            "tasks": tasks,
        }
    return schema


PROCESSOR_SCHEMAS = {kind: component_schema(kind, component, processor=True) for kind, component in PROCESSORS.items()}
SERVICE_SCHEMAS = {kind: component_schema(kind, component) for kind, component in CONTROLLER_SERVICES.items()}


def available_relationships(kind, properties, dynamic):
    available = set(PROCESSORS[kind]["relationships"])
    if kind == "DistributeLoad":
        number = str(properties.get("Number of Relationships", "1"))
        if re.fullmatch(r"[0-9]{1,3}", number):
            available = {str(i) for i in range(1, int(number) + 1)}
    elif kind == "RouteOnAttribute" and properties.get("Routing Strategy", "Route to Property name") != "Route to Property name":
        available.add("matched")
    elif kind == "RouteText" and properties.get("Routing Strategy", "Route to each matching Property Name") != "Route to each matching Property Name":
        available.add("matched")
    elif PROCESSORS[kind].get("dynamicRelationship"):
        available.update(dynamic)
    return available


def requirement_applies(field, values):
    return all(name in values and values[name] != "" and (not options or values[name] in options)
               for name, options in field["dependencies"].items())


def property_text(value):
    if isinstance(value, bool):
        return str(value).lower()
    if type(value) is int or (type(value) is float and math.isfinite(value)):
        return str(value)
    if isinstance(value, str) and len(value) <= 32768 and "\x00" not in value:
        return value
    raise ValueError("Use a finite scalar value of at most 32768 characters.")


def validate_secret_fields(definition, processors=PROCESSOR_SCHEMAS, services=SERVICE_SCHEMAS):
    errors = []
    for entries, schemas in ((definition.get("nodes", []), processors),
                             (definition.get("controller_services", []), services)):
        for entry in entries:
            fields = schemas.get(entry["type"], {}).get("properties", {})
            for values in (entry.get("config", {}), entry.get("attributes", {})):
                for name, value in values.items():
                    if fields.get(name, {}).get("sensitive") and value not in (None, ""):
                        errors.append(f"Component {entry['id']}, {name}: sensitive values cannot be stored in a draft.")
    return errors


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


def resolve_properties(component, schema, services, scope, errors, *, defaults=None):
    fields = schema["properties"]
    config = component.get("config", {})
    raw = {key: field["default"] for key, field in fields.items() if "default" in field}
    overrides = {}
    for key, value in config.items():
        field = fields.get(key)
        if field is None:
            errors.append(f"{scope}, {key}: unknown property. Use Dynamic properties when available.")
            continue
        if field["sensitive"]:
            if value not in ("", None):
                errors.append(f"{scope}, {key}: sensitive values are unavailable.")
            continue
        try:
            value = checked_value(value, field) if field.get("legacy") else property_text(value)
            value = property_text(value)
            expression = "${" in value
            if "#{" in value:
                raise ValueError("Parameter contexts are unavailable.")
            if expression and field["expression_scope"] == "NONE":
                raise ValueError("This property does not support Expression Language.")
            if not expression:
                validate_native_literal(value, field.get("validator"))
            if field.get("choices") and not expression and value not in field["choices"]:
                if field["type"] == "boolean":
                    value = next((option for option in field["choices"] if option.lower() == value.lower()), value)
                if value not in field["choices"]:
                    raise ValueError("Choose a supported value.")
            if field["type"] == "service" and value and field["service"] not in services.get(value, set()):
                raise ValueError("Select a configured compatible controller service.")
            overrides[key] = value
        except ValueError as exc:
            errors.append(f"{scope}, {key}: {exc}")
    effective = {key: property_text(value) for key, value in (raw | overrides).items()}
    for key, field in fields.items():
        if field["required"] and requirement_applies(field, effective) and not effective.get(key):
            message = "required sensitive property cannot be supplied." if field["sensitive"] else "enter a required value."
            errors.append(f"{scope}, {key}: {message}")
    dynamic = component.get("attributes", {})
    if dynamic and not schema["dynamic_properties"]:
        errors.append(f"{scope}: this component has no declared dynamic properties.")
    for key, value in dynamic.items():
        if not key.strip() or len(key) > 512 or "\x00" in key or key in fields:
            errors.append(f"{scope}, {key}: enter a distinct dynamic property name.")
            continue
        try:
            if component["type"] == "GenerateFlowFile":
                if not ATTRIBUTE_NAME.fullmatch(key):
                    raise ValueError("Enter a valid FlowFile attribute name.")
                value = checked_value(value, {"type": "text", "max": 256})
            if "#{" in value:
                raise ValueError("Parameter contexts are unavailable.")
            if "${" in value and not any(
                descriptor.get("expressionLanguageScope", "NONE") != "NONE" for descriptor in schema.get("dynamic", [])
            ):
                raise ValueError("This dynamic property does not support Expression Language.")
            overrides[key] = property_text(value)
        except ValueError as exc:
            errors.append(f"{scope}, {key}: {exc}")
    if component["type"] == "GenerateFlowFile" and "Custom Text" in overrides and (
        effective.get("Data Format") != "Text" or effective.get("Unique FlowFiles") == "true"
    ):
        errors.append(f"{scope}, Custom Text: choose Text and turn off Unique FlowFiles.")
    # Use NiFi's own defaults for the bundled components. Preserve OEM's previously published legacy defaults.
    if defaults is None:
        defaults = {key: property_text(field["default"]) for key, field in
                    LEGACY_PROPERTIES.get(component["type"], {}).get("properties", {}).items() if "default" in field}
    return defaults | overrides, effective


def validate_native_literal(value, validator):
    if validator == "NON_BLANK_VALIDATOR" and not value.strip():
        raise ValueError("Enter a non-blank value.")
    if validator in NATIVE_INTEGER_FORMATS:
        pattern, minimum, maximum = NATIVE_INTEGER_FORMATS[validator]
        if not re.fullmatch(pattern, value) or not minimum <= int(value) <= maximum:
            raise ValueError(f"Use an integer from {minimum} to {maximum}.")


def resolve_processor(node, services, errors):
    scope = f"Node {node['id']}"
    schema = PROCESSOR_SCHEMAS[node["type"]]
    props, effective = resolve_properties(node, schema, services, scope, errors)
    scheduling = resolve_fields(node.get("scheduling", {}), schema["scheduling"], scope, errors)
    return props, scheduling, available_relationships(node["type"], effective, node.get("attributes", {}))
