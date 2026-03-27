from pydantic import BaseModel, Field


class AppQueueNetworkProfileRequest(BaseModel):
    ssid: str = Field(min_length=1, max_length=64)
    password: str = Field(default="", max_length=128)
    source: str = Field(default="app_manual", max_length=64)


class AppQueueNetworkProfileResponse(BaseModel):
    status: str
    expires_in_seconds: int


class DeviceNetworkProfilePullResponse(BaseModel):
    status: str
    ssid: str | None = None
    password: str | None = None
    source: str | None = None
