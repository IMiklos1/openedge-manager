class MinifiC2Adapter:
    # Adapter contract only. Implement the official MiNiFi C2 wire protocol and
    # contract-test it against the exact pinned MiNiFi C++ release.
    def parse_heartbeat(self, payload: dict) -> dict:
        raise NotImplementedError("Implement C2 heartbeat parsing.")

    def build_heartbeat_response(self, agent_id: str) -> dict:
        raise NotImplementedError("Implement C2 response structure and operations.")

    def process_acknowledgement(self, payload: dict) -> None:
        raise NotImplementedError("Implement C2 ACK handling.")
