from pydantic import BaseModel, ConfigDict, Field

from app.roles import Role
from app.schemas.profile import ProfileCreate, ProfileRead, ProfileUpdate


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=8)
    profile: ProfileCreate


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str | None = None
    password: str | None = Field(default=None, min_length=8)
    profile: ProfileUpdate | None = None


class UserRead(BaseModel):
    id: int
    username: str
    role: Role
    profile: ProfileRead

    model_config = ConfigDict(from_attributes=True)


class RoleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Role
