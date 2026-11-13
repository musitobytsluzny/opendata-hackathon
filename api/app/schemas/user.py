from pydantic import BaseModel, ConfigDict, Field

from app.schemas.profile import ProfileCreate, ProfileRead, ProfileUpdate


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=8)
    profile: ProfileCreate


class UserUpdate(BaseModel):
    username: str | None = None
    password: str | None = Field(default=None, min_length=8)
    profile: ProfileUpdate | None = None


class UserRead(BaseModel):
    id: int
    username: str
    profile: ProfileRead

    model_config = ConfigDict(from_attributes=True)
