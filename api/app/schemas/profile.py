from pydantic import BaseModel, ConfigDict, Field


class ProfileCreate(BaseModel):
    firstname: str = Field(min_length=1, max_length=100)
    lastname: str = Field(min_length=1, max_length=100)


class ProfileUpdate(BaseModel):
    firstname: str | None = None
    lastname: str | None = None


class ProfileRead(BaseModel):
    id: int
    firstname: str
    lastname: str

    model_config = ConfigDict(from_attributes=True)
