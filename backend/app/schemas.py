from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    email: EmailStr


class ConnectionTest(BaseModel):
    url: str = Field(min_length=8, max_length=2000)


class ConnectionCreate(ConnectionTest):
    name: str = Field(min_length=1, max_length=100)


class ConnectionOut(BaseModel):
    """Never exposes the URL (it contains credentials)."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    db_type: str
    created_at: datetime


class ConnectionTestOut(BaseModel):
    ok: bool = True
    schema_preview: str


class SessionCreate(BaseModel):
    connection_id: str


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    connection_id: str
    title: str
    created_at: datetime


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
    id: str
    session_id: str
    seq: int
    role: str
    content: str
    query: str | None = None
    result: dict[str, Any] | None = Field(default=None, validation_alias="result_json")
    attempts: list[dict[str, Any]] | None = Field(default=None, validation_alias="attempts_json")
    status: str
    created_at: datetime


class SessionDetail(SessionOut):
    messages: list[MessageOut]


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
