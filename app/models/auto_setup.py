"""Smart Setup models — one-shot secure protocol stack generation.

The engine is a local heuristic (latency measurement + REALITY key
generation); no external AI service is contacted.
"""

import re

from pydantic import BaseModel, Field, field_validator

DOMAIN_PATTERN = re.compile(
    r"^(?=.{1,253}$)([a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$"
)


class SmartSetupRequest(BaseModel):
    domain: str = Field(min_length=4, max_length=253)
    base_port: int = Field(default=443, ge=1, le=65535)
    node_id: int | None = None
    include_vmess: bool | None = None  # None = decide from the latency profile

    @field_validator("domain")
    @classmethod
    def validate_domain(cls, v: str) -> str:
        v = v.strip().lower()
        if not DOMAIN_PATTERN.fullmatch(v):
            raise ValueError("domain must be a valid hostname like panel.example.com")
        return v


class SmartSetupInboundReport(BaseModel):
    tag: str
    port: int
    protocol: str
    security: str
    remark: str


class SmartSetupResponse(BaseModel):
    ok: bool
    profile: str
    profile_reason: str
    node_latency_ms: float | None = None
    internet_latency_ms: float | None = None
    core_id: int
    core_name: str
    group_id: int
    group_name: str
    host_count: int
    inbounds: list[SmartSetupInboundReport]
    ports_to_open: list[int]
    security_notes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
