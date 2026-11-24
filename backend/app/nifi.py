"""Read the internal NiFi Site-to-Site catalog without accepting client-supplied URLs."""

import json
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel

from .config import settings


class InputPort(BaseModel):
    id: UUID
    name: str


class Controller(BaseModel):
    inputPorts: list[InputPort] | None = None
    remoteSiteHttpListeningPort: int


class SiteToSiteCatalog(BaseModel):
    controller: Controller


class RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def input_ports() -> list[InputPort]:
    if not settings.oem_nifi_url:
        raise HTTPException(503, "Internal NiFi is not configured. Start the NiFi Compose overlay.")

    request = Request(
        f"{str(settings.oem_nifi_url).rstrip('/')}/nifi-api/site-to-site",
        headers={"Accept": "application/json", "x-nifi-site-to-site-protocol-version": "1"},
    )
    opener = build_opener(ProxyHandler({}), RejectRedirects())
    limit = 1024 * 1024
    try:
        with opener.open(request, timeout=5) as response:
            body = response.read(limit + 1)
        if len(body) > limit:
            raise ValueError("Input Port catalog exceeds its size limit")
        controller = SiteToSiteCatalog.model_validate(json.loads(body)).controller
    except (OSError, ValueError) as exc:
        raise HTTPException(503, "Internal NiFi HTTP Site-to-Site catalog is unavailable.") from exc

    return sorted(controller.inputPorts or [], key=lambda port: (port.name.casefold(), str(port.id)))
