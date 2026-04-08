from pydantic import BaseModel


class ContactUploadResponse(BaseModel):
    contacts_added: int
    contacts_skipped: int
