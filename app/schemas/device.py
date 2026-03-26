from pydantic import BaseModel, Field


class DeviceRegisterRequest(BaseModel):
    device_code: str = Field(min_length=3, max_length=128)
    secret: str = Field(min_length=8, max_length=255)


class DeviceAuthRequest(BaseModel):
    device_code: str = Field(min_length=3, max_length=128)
    secret: str = Field(min_length=8, max_length=255)


class DeviceResponse(BaseModel):
    id: str
    device_code: str
    is_active: bool


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int
