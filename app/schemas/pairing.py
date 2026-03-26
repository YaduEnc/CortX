from datetime import datetime

from pydantic import BaseModel, Field


class PairingStartRequest(BaseModel):
    device_code: str = Field(min_length=3, max_length=128)
    pair_nonce: str = Field(min_length=8, max_length=128)


class PairingStartResponse(BaseModel):
    pairing_session_id: str
    pair_token: str
    expires_at: datetime


class PairingCompleteRequest(BaseModel):
    pair_token: str = Field(min_length=16, max_length=512)


class PairingCompleteResponse(BaseModel):
    status: str
    pairing_session_id: str
    user_id: str
