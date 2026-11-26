"""Generate the OEM MiNiFi C++ catalog from the official binaries' --manifest output."""

import argparse
import json
from pathlib import Path


def property_descriptor(descriptor):
    result = {
        "description": descriptor["description"],
        "required": descriptor["required"] == "true",
        "sensitive": descriptor["sensitive"] == "true",
        "expressionLanguageScope": descriptor["expressionLanguageScope"],
    }
    for name in ("displayName", "defaultValue", "validator"):
        if name in descriptor:
            result[name] = descriptor[name]
    if "allowableValues" in descriptor:
        result["choices"] = descriptor["allowableValues"]
    if "typeProvidedByValue" in descriptor:
        result["service"] = descriptor["typeProvidedByValue"]["type"]
    return result


def component_descriptor(item, bundle, processor):
    descriptor = {
        "type": item["type"],
        "bundle": bundle,
        "description": item["typeDescription"],
        "properties": {name: property_descriptor(prop) for name, prop in item.get("propertyDescriptors", {}).items()},
        "dynamic": item["supportsDynamicProperties"] == "true",
    }
    if processor:
        descriptor.update(
            inputRequirement=item["inputRequirement"],
            triggerSerially=item["isSingleThreaded"] == "true",
            relationships={rel["name"]: {"description": rel["description"]}
                           for rel in item.get("supportedRelationships", [])},
            dynamicRelationship=item["supportsDynamicRelationships"] == "true",
        )
    else:
        types = {item["type"], *(api["type"] for api in item.get("providedApiImplementations", []))}
        descriptor["apis"] = [{"className": name} for name in sorted(types)]
    return descriptor


def merge_component(destination, item, bundle, processor, platform):
    short_name = item["type"].rsplit(".", 1)[-1]
    candidate = component_descriptor(item, bundle, processor)
    fields = candidate.pop("properties")
    saved = destination.setdefault(short_name, candidate | {"platforms": [], "properties": {}})
    if candidate != {key: saved[key] for key in saved if key not in ("platforms", "properties")}:
        raise ValueError(f"Conflicting component definitions for {short_name}")
    saved["platforms"].append(platform)
    for name, field in fields.items():
        previous = saved["properties"].setdefault(name, field | {"platforms": []})
        if field != {key: value for key, value in previous.items() if key != "platforms"}:
            raise ValueError(f"Conflicting property definitions for {short_name}.{name}")
        previous["platforms"].append(platform)


def collect(linux, windows):
    sections = {"processors": {}, "services": {}}
    versions = set()
    for platform, path in (("Linux", linux), ("Windows", windows)):
        bundles = json.loads(path.read_text(encoding="utf-8-sig"))
        seen = set()
        for entry in bundles:
            bundle = {key: entry["bundles"][key] for key in ("group", "artifact", "version")}
            if bundle["artifact"] == "minifi-standard-processors":
                versions.add(bundle["version"])
            manifest = entry["bundles"]["componentManifest"]
            for section, wire_key in (("processors", "processors"), ("services", "controllerServices")):
                for item in manifest.get(wire_key, []):
                    identity = section, item["type"]
                    if identity in seen:
                        raise ValueError(f"Duplicate {platform} component: {item['type']}")
                    seen.add(identity)
                    merge_component(sections[section], item, bundle, section == "processors", platform)
        if not seen:
            raise ValueError(f"No components found in the {platform} manifest")
    version, = versions
    for entries in sections.values():
        for component in entries.values():
            for field in component["properties"].values():
                if field["platforms"] == component["platforms"]:
                    del field["platforms"]
    return version, sections


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("linux", type=Path)
    parser.add_argument("windows", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    version, sections = collect(args.linux, args.windows)
    parts = [f'  "runtime_version": {json.dumps(version)}']
    for section, entries in sections.items():
        lines = [f"    {json.dumps(key)}: {json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))}"
                 for key, value in sorted(entries.items())]
        parts.append(f'  "{section}": {{\n' + ",\n".join(lines) + "\n  }")
    args.output.write_text("{\n" + ",\n".join(parts) + "\n}\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
