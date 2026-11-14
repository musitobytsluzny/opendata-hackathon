from pydantic import BaseModel, ConfigDict, model_validator

from app.roles import Role
from app.schemas.fields import Password, Username
from app.schemas.profile import ProfileCreate, ProfileRead, ProfileUpdate


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: Username
    password: Password
    profile: ProfileCreate


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: Username | None = None
    password: Password | None = None
    profile: ProfileUpdate | None = None

    @model_validator(mode="after")
    def reject_explicit_null_credentials(self):
        for key in ("username", "password"):
            if key in self.model_fields_set and getattr(self, key) is None:
                raise ValueError(f"{key} nesmí být null")
        return self


class UserRead(BaseModel):
    id: int
    username: str
    role: Role
    profile: ProfileRead

    model_config = ConfigDict(from_attributes=True)


class RoleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Role
