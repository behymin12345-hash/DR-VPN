"""Request models for the proxy-workspace client endpoints.

Kept deliberately small: the proxy page only needs the fields a proxy
operator actually manages. Users are created/modified through the same
validators as the regular user flow (username rules, limits, …).
"""

from pydantic import BaseModel, Field, field_validator

from app.models.user import UserValidator


class ProxyClientCreate(BaseModel):
    username: str
    group_ids: list[int] | None = Field(default=None)
    data_limit: int | None = Field(default=None, ge=0)
    expire: int | None = Field(default=None, ge=0)
    usage_coefficient: float | None = Field(default=None, ge=0, le=100)
    note: str | None = None

    @field_validator("username")
    @classmethod
    def validate_username(cls, v):
        return UserValidator.validate_username(v)


class ProxyClientModify(BaseModel):
    group_ids: list[int] | None = Field(default=None)
    data_limit: int | None = Field(default=None, ge=0)
    expire: int | None = Field(default=None, ge=0)
    usage_coefficient: float | None = Field(default=None, ge=0, le=100)
    note: str | None = None
    status: str | None = Field(default=None, pattern="^(active|disabled|on_hold)$")
