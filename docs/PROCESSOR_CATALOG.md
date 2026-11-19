# MiNiFi Java processor catalog

The default Apache MiNiFi Java 2.12.0 image contains 117 processors and 47 controller
services. The designer reads the descriptors packaged in these NARs through the management
API. The entries carry the component class, bundle coordinates, property keys, display
names, defaults, allowed values, dependencies, Expression Language scopes, service
interfaces, input requirements and relationship definitions. OEM keeps its existing
limits and defaults for GenerateFlowFile and LogAttribute.

To regenerate the catalog from the repository root with Bash:

```bash
image=apache/nifi-minifi:2.12.0@sha256:ad599a28a8955ac6bc9b4f5839a767241e20efa406975aedd9c620c4f4a08578
docker pull "$image"
catalog_work=$(mktemp -d)
catalog_container=$(docker create "$image")
mkdir "$catalog_work/lib"
docker cp "${catalog_container}:/opt/minifi/minifi-current/lib/." "$catalog_work/lib"
docker rm "$catalog_container"
python3 scripts/extract-minifi-catalog.py "$catalog_work/lib" backend/app/minifi_catalog.json
```

The generated metadata derives from the packaged `META-INF/docs/extension-manifest.xml`
files. Apache NiFi, Copyright 2014–2026 The Apache Software Foundation. This product
includes software developed at The Apache Software Foundation. The catalog normalizes
the source metadata for OEM. [Apache License 2.0](licenses/Apache-2.0.txt) ·
[Apache NiFi release source](https://github.com/apache/nifi/tree/19f4df8e048e91d87d3e4967c69b1298f9dbe450)

## Author and deploy

Search by processor name or tag. Use Properties for static settings and declared dynamic
properties. The Relationships tab offers explicit termination and retry. Automatic
termination of unconnected relationships is the default. Use the canvas or the source
and destination selectors to add a connection. Select the source relationship in the
connection inspector. Create a controller service from its own selector, then reference
it in compatible processor or service properties.

Published artifacts use the Java raw JSON flow format, with deterministic component IDs,
exact bundle coordinates and settings for a standalone timer-driven agent. OEM validates
the graph, known fields, required values, enumerations and service references. Custom
NiFi validators still run on the device. Files, listeners, drivers and external services
need the corresponding configuration and resources on the target agent. The catalog entry
indicates bundle availability. See the implementation plan for runtime test coverage.

A device must run Java 2.12.0, be explicitly enabled on the server, and check in with
a C2 manifest advertising each processor and controller service in the published artifact.
The browser chooses a registered target and queues the update. The device downloads it
over outbound C2. Enable command-executing processors separately on a trusted development
stack. [Security and deployment boundaries](SECURITY.md)

Sensitive property names are visible. The editor and API block storing their values
in a draft. External secret provisioning, parameter contexts, process groups, custom
NARs and shared scheduling strategies outside the standalone timer-driven profile
remain open. Execution of the entire processor catalog has not been qualified on
real external systems. [Implementation plan](IMPLEMENTATION_PLAN.md)
