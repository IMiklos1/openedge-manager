# Capability status must be verified against the exact pinned MiNiFi C++ build.
CATALOG = {
    "GetFile": {"category": "Files", "runtime": ["minifi-cpp"], "status": "VERIFY_BUILD"},
    "TailFile": {"category": "Files", "runtime": ["minifi-cpp"], "status": "VERIFY_BUILD"},
    "PutFile": {"category": "Files", "runtime": ["minifi-cpp"], "status": "VERIFY_BUILD"},
    "InvokeHTTP": {"category": "HTTP", "runtime": ["minifi-cpp"], "status": "VERIFY_BUILD"},
    "ListenTCP": {"category": "TCP", "runtime": ["minifi-cpp"], "status": "VERIFY_BUILD"},
    "ListenUDP": {"category": "TCP", "runtime": ["minifi-cpp"], "status": "VERIFY_BUILD"},
    "PublishMQTT": {"category": "MQTT", "runtime": ["minifi-cpp"], "status": "VERIFY_BUILD"},
    "ConsumeMQTT": {"category": "MQTT", "runtime": ["minifi-cpp"], "status": "VERIFY_BUILD"},
    "ExecuteSQL": {"category": "SQL", "runtime": ["minifi-cpp"], "status": "VERIFY_BUILD"},
    "PublishKafka": {"category": "Kafka", "runtime": ["minifi-cpp"], "status": "VERIFY_BUILD"},
    "ConsumeKafka": {"category": "Kafka", "runtime": ["minifi-cpp"], "status": "VERIFY_BUILD"},
    "ModbusRead": {"category": "Modbus", "runtime": ["custom-extension"], "status": "NOT_IMPLEMENTED"},
    "OPCUARead": {"category": "OPC UA", "runtime": ["custom-extension"], "status": "NOT_IMPLEMENTED"}
}
