"""Generate the OEM catalog from Apache MiNiFi Java's packaged NAR manifests."""

import argparse
import json
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile

MANIFEST = "META-INF/docs/extension-manifest.xml"
VERSION = "2.12.0"


def fields(element, names):
    return {name: value for name in names if (value := element.findtext(name)) is not None}


def property_descriptor(element):
    data = fields(element, ["displayName", "description", "defaultValue", "expressionLanguageScope"])
    for name in ("required", "sensitive", "dynamicallyModifiesClasspath"):
        if element.findtext(name) == "true":
            data[name] = True
    options = element.findall("allowableValues/allowableValue")
    if options:
        data["choices"] = [fields(value, ["value", "displayName", "description"]) for value in options]
    dependencies = element.findall("dependencies/dependency")
    if dependencies:
        data["dependencies"] = {
            item.findtext("propertyName"): [value.text for value in item.findall("dependentValues/dependentValue")]
            for item in dependencies
        }
    service = element.find("controllerServiceDefinition")
    if service is not None:
        data["service"] = service.findtext("className")
    return data


def load_components(directory):
    components = {"processors": {}, "services": {}}
    for nar in sorted(directory.glob("*.nar")):
        with ZipFile(nar) as archive:
            root = ElementTree.fromstring(archive.read(MANIFEST))
        bundle = {key: root.findtext(tag) for key, tag in (
            ("group", "groupId"), ("artifact", "artifactId"), ("version", "version"),
        )}
        if bundle["version"] != VERSION:
            raise ValueError(f"Unexpected NAR version in {nar.name}")
        for element in root.findall("extensions/extension"):
            extension_type = element.findtext("type")
            if extension_type not in {"PROCESSOR", "CONTROLLER_SERVICE"}:
                continue
            class_name = element.findtext("name")
            collection = components["processors" if extension_type == "PROCESSOR" else "services"]
            name = class_name.rsplit(".", 1)[-1]
            if name in collection:
                raise ValueError(f"Duplicate component name {name}")
            data = fields(element, ["description", "inputRequirement"])
            data.update(type=class_name, bundle=bundle, tags=[tag.text for tag in element.findall("tags/tag")])
            data["properties"] = {
                prop.findtext("name"): property_descriptor(prop) for prop in element.findall("properties/property")
            }
            dynamic = element.findall("dynamicProperties/dynamicProperty")
            if dynamic:
                data["dynamic"] = [fields(p, ["name", "description", "value", "expressionLanguageScope"]) for p in dynamic]
            for tag in ("supportsSensitiveDynamicProperties", "triggerSerially", "primaryNodeOnly"):
                if element.findtext(tag) == "true":
                    data[tag] = True
            if extension_type == "PROCESSOR":
                data["relationships"] = {
                    rel.findtext("name"): fields(rel, ["description", "autoTerminated"])
                    for rel in element.findall("relationships/relationship")
                }
                if (relationship := element.find("dynamicRelationship")) is not None:
                    data["dynamicRelationship"] = fields(relationship, ["name", "description"])
                if (schedule := element.find("defaultSchedule")) is not None:
                    data["defaultSchedule"] = fields(schedule, ["strategy", "period", "concurrentTasks"])
            else:
                data["apis"] = [fields(api, ["className", "groupId", "artifactId", "version"])
                                for api in element.findall("providedServiceAPIs/providedServiceAPI")]
            collection[name] = data
    if not all(components.values()):
        raise ValueError("No bundled processors or controller services found")
    return components


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("nar_directory", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    components = load_components(args.nar_directory)
    groups = []
    for group, entries in components.items():
        rows = [f"    {json.dumps(name)}: {json.dumps(entry, ensure_ascii=False, separators=(',', ':'))}"
                for name, entry in sorted(entries.items())]
        groups.append('  ' + json.dumps(group) + ': {\n' + ',\n'.join(rows) + '\n  }')
    args.output.write_text('{\n' + f'  "runtime_version": "{VERSION}",\n' + ',\n'.join(groups) + '\n}\n',
                           encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
