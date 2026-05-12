from pydantic import BaseModel, ConfigDict, Field


class TagCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    color: str | None = Field(default=None, max_length=16)


class TagResponse(BaseModel):
    id: int
    name: str
    color: str | None

    model_config = ConfigDict(from_attributes=True)

