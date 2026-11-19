"""Metadata from the stock Apache MiNiFi Java image. See docs/PROCESSOR_CATALOG.md."""

import json
from pathlib import Path

_catalog = json.loads(Path(__file__).with_name("minifi_catalog.json").read_text(encoding="utf-8"))
MINIFI_VERSION = _catalog["runtime_version"]
PROCESSORS = _catalog["processors"]
CONTROLLER_SERVICES = _catalog["services"]

# Retain the protocol placeholders used by existing saved drafts.
UNBUNDLED = {
    "ModbusRead": "Modbus", "OPCUARead": "OPC UA", "ConsumeKafka": "Kafka", "PublishKafka": "Kafka",
}
