from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AttributeDefinitionCreateRequest(BaseModel):
    key: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=120)
    type: str = Field(default="text", pattern=r"^(text|number|boolean|date)$")
    is_indexed: bool = False


class AttributeDefinitionResponse(BaseModel):
    id: int
    key: str
    label: str
    type: str
    is_indexed: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ContactAttributeUpsertRequest(BaseModel):
    key: str = Field(min_length=1, max_length=64)
    value_text: str | None = None
    value_number: float | None = None
    value_bool: bool | None = None
    value_date_iso: str | None = None


class ContactAttributeValueResponse(BaseModel):
    attribute_definition_id: int
    key: str
    type: str
    value_text: str | None
    value_number: float | None
    value_bool: bool | None
    value_date_iso: str | None
    updated_at: datetime

