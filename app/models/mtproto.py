from pydantic import BaseModel, ConfigDict, Field, field_validator


class MtprotoProxyBase(BaseModel):
    name: str = Field(max_length=64)
    server: str = Field(max_length=255)
    port: int = Field(ge=1, le=65535)
    secret: str = Field(max_length=160)
    enabled: bool = True

    @field_validator("name", "server", "secret")
    @classmethod
    def strip_non_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value can't be empty")
        return value


class MtprotoProxyCreate(MtprotoProxyBase):
    pass


class MtprotoProxyModify(MtprotoProxyBase):
    pass


class MtprotoProxyResponse(MtprotoProxyBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
