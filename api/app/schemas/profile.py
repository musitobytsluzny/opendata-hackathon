from pydantic import BaseModel, ConfigDict, model_validator

from app.schemas.fields import PersonName


class ProfileCreate(BaseModel):
    firstname: PersonName
    lastname: PersonName


class ProfileUpdate(BaseModel):
    firstname: PersonName | None = None
    lastname: PersonName | None = None

    @model_validator(mode="after")
    def reject_null_names(self):
        for key in ("firstname", "lastname"):
            if key in self.model_fields_set and getattr(self, key) is None:
                raise ValueError(f"{key} nesmí být null")
        return self


class ProfileRead(BaseModel):
    id: int
    firstname: str
    lastname: str

    model_config = ConfigDict(from_attributes=True)
