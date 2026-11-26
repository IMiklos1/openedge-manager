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

## MiNiFi C++ 1.1.0 catalog

The native catalog combines 94 processors and 22 controller services from Apache
MiNiFi C++ 1.1.0. The pinned Linux amd64 image advertises 88 processors and 21 services.
The Windows x86-64 MSI contains 87 processors and 20 services. This adds Windows-specific
SMB, event log and performance counter processors to the same C++ workspace.

The Flow Manager exposes the native bundle coordinates, required and sensitive fields,
defaults, choices, validators, dynamic properties, relationship names and controller service
references. The inspector identifies platform-specific settings. Publication uses the
native JSON flow format. Deployment requires matching components in the target's full C2
manifest, including their exact bundle versions. A configured platform-specific property
also requires matching OS inventory. Processor configuration, external services and
availability depend on the installed extensions and the target environment.

To regenerate from the pinned Linux image and Windows release, capture the Linux manifest
in PowerShell 7.4 or later from the repository root:

~~~powershell
$cppLinuxImage = "apache/nifi-minifi-cpp:1.1.0@sha256:647d0548f8411aeb7fc58def0666077c25f950ba85cf5cc58d4d28500b58e0cd"
docker run --rm --platform linux/amd64 --entrypoint bin/minifi $cppLinuxImage --manifest > cpp-linux-manifest.json
~~~

Use the Apache [Windows x86-64 MSI release](https://archive.apache.org/dist/nifi/nifi-minifi-cpp-1.1.0/).
The release MSI SHA-512 is
~~~text
e3c4194b453c5e12d6c1132cf9a2a68c96085ca22ef0f1ca19209c8eedab862811d02d567aa073104e28f614ebadcdd04cf1e0b33878dcb8ae036ce7622475eb
~~~
Select the packaged extensions during installation or extract the full MSI, then run the
agent binary from the installation directory. Adjust the installation path if needed:

~~~powershell
$cppWindowsManifest = Join-Path (Get-Location).Path "cpp-windows-manifest.json"
Push-Location "$env:ProgramFiles\ApacheNiFiMiNiFi\nifi-minifi-cpp"
try {
    & .\bin\minifi.exe --manifest > $cppWindowsManifest
} finally {
    Pop-Location
}
python scripts/extract-minifi-cpp-catalog.py cpp-linux-manifest.json cpp-windows-manifest.json backend/app/minifi_cpp_catalog.json
git diff --exit-code -- backend/app/minifi_cpp_catalog.json
~~~

The C++ metadata derives from [Apache NiFi MiNiFi C++ release source](https://github.com/apache/nifi-minifi-cpp/tree/1a4b84eb8b53eebcf7c92d83f6ae818f440e33ee),
Copyright The Apache Software Foundation, under the [Apache License 2.0](licenses/Apache-2.0.txt).

The stock catalog includes `ExecuteScript` with Python and Lua engines. When an operator
configures a script file, provision it and its dependencies on the agent first. On native
Windows, enable the MSI Python extension and install Python for the Windows service account.
Deployment of `ExecuteScript` and `ExecuteProcess` requires the separate
`MINIFI_ALLOW_EXECUTION_PROCESSORS=true` opt-in. Custom extensions and Python processor
packages require installation outside OEM. Custom processors absent from the pinned
manifests, runtime-specific scheduling outside timer-driven, and native relationship retry
settings are outside this editor profile.
