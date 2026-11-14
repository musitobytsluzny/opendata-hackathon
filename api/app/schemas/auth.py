from pydantic import BaseModel, Field

from app.schemas.fields import Username


class LoginRequest(BaseModel):
    username: Username
    password: str = Field(min_length=1, max_length=1024)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
