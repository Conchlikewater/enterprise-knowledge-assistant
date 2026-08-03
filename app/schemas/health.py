"""Health endpoint response model."""

from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str
    version: str
    components: dict[str, Literal["ok", "configured"]]
