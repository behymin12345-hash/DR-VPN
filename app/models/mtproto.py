from pydantic import BaseModel, ConfigDict, Field, field_validator

import re


class MtprotoProxyBase(BaseModel):
    name: str = Field(max_length=64)
    server: str = Field(max_length=255)
    port: int = Field(ge=1, le=65535)
    secret: str = Field(max_length=160)
    enabled: bool = True
    sponsored_channel: str | None = Field(default=None, max_length=255)
    tag: str | None = Field(default=None, max_length=64)
    node_id: int | None = Field(default=None)

    @field_validator("name", "server", "secret")
    @classmethod
    def strip_non_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value can't be empty")
        return value

    @field_validator("sponsored_channel")
    @classmethod
    def validate_channel(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            return None
        if not (value.startswith("@") or value.startswith("https://t.me/") or value.lstrip("-").isdigit()):
            raise ValueError("sponsored channel must be @username, a t.me link or a numeric channel id")
        return value

    @field_validator("tag")
    @classmethod
    def validate_tag(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip().lower()
        if value and not re.fullmatch(r"[0-9a-f]{16}", value):
            raise ValueError("tag must be the 16 hex characters @MTProxybot gives you")
        return value or None


class MtprotoProxyCreate(MtprotoProxyBase):
    admin_id: int | None = Field(default=None)


class MtprotoProxyModify(MtprotoProxyBase):
    pass


class MtprotoProxyResponse(MtprotoProxyBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    admin_id: int | None = None
