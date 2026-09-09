from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AlertChannelBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    channel_type: str = Field(..., min_length=1, max_length=50)
    is_enabled: bool = True
    config: Dict[str, Any]
    endpoint_ids: List[UUID] = Field(default_factory=list)
    subnet_filters: List[str] = Field(default_factory=list)
    severity_filters: List[str] = Field(default_factory=lambda: ["DOWN", "RECOVERED"])

    model_config = ConfigDict(from_attributes=True)


class AlertChannelCreate(AlertChannelBase):
    pass


class AlertChannelUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    channel_type: Optional[str] = Field(default=None, min_length=1, max_length=50)
    is_enabled: Optional[bool] = None
    config: Optional[Dict[str, Any]] = None
    endpoint_ids: Optional[List[UUID]] = None
    subnet_filters: Optional[List[str]] = None
    severity_filters: Optional[List[str]] = None

    model_config = ConfigDict(from_attributes=True)


class AlertChannelResponse(BaseModel):
    id: UUID
    name: str
    channel_type: str
    is_enabled: bool
    config: Dict[str, Any]
    endpoint_ids: List[UUID]
    subnet_filters: List[str]
    severity_filters: List[str]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AlertTestRequest(BaseModel):
    channel_id: Optional[UUID] = None
    channel_type: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    name: Optional[str] = None


class AlertDeliveryLogResponse(BaseModel):
    id: UUID
    channel_id: UUID
    channel_name: str
    endpoint_id: Optional[UUID] = None
    endpoint_name: str
    event_type: str
    status: str
    status_code: Optional[int] = None
    retry_count: int = 0
    response_message: Optional[str] = None
    delivered_at: datetime

    model_config = ConfigDict(from_attributes=True)
