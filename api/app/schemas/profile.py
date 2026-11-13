
from pydantic import BaseModel, ConfigDict


class ProfileCreate(BaseModel):
    firstname: str
    lastname: str


class ProfileUpdate(BaseModel):
    firstname: str | None = None
    lastname: str | None = None


class ProfileRead(BaseModel):
    id: int
    firstname: str
    lastname: str

    model_config = ConfigDict(from_attributes=True)
