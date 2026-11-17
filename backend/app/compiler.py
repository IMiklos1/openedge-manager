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

def compile_minifi_cpp_yaml(definition: dict) -> str:
    errors = validate_flow(definition)
    if errors:
        raise CompileError("; ".join(errors))
    raise NotImplementedError(
        "Compiler is a deliberate stub. Implement against the pinned MiNiFi C++ YAML schema."
    )
