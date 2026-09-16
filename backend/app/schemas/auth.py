from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.common import validate_phone_number
from app.schemas.user import UserResponse


class RegisterRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    # bcrypt only looks at the first 72 bytes, so longer passwords are rejected.
    password: str = Field(min_length=8, max_length=72)
    phone_number: str | None = None

    @field_validator("phone_number")
    @classmethod
    def check_phone_number(cls, value: str | None) -> str | None:
        return validate_phone_number(value)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=72)


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse
