import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AuthUserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    name: str
    created_at: datetime


class AuthResponse(BaseModel):
    access_token: str
    token_type: str
    user: AuthUserOut