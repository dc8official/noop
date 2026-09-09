from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings as app_cfg
from app.database import get_db
from app.models.system_setting import AppSetting
from app.routers.auth import get_current_user, require_admin
from app.schemas import APIResponse
from app.services.driver_manager import driver_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["settings"])


class SettingsUpdate(BaseModel):
    performance_mode: Optional[bool] = None
    performanceMode: Optional[bool] = None
    l2_auto_bypass: Optional[bool] = None
    l2AutoBypass: Optional[bool] = None
    session_timeout: Optional[int] = Field(default=None, ge=1, le=1440)
    sessionTimeout: Optional[int] = Field(default=None, ge=1, le=1440)
    lockout_threshold: Optional[int] = Field(default=None, ge=1, le=100)
    lockoutThreshold: Optional[int] = Field(default=None, ge=1, le=100)
    alerting_enabled: Optional[bool] = None
    alertingEnabled: Optional[bool] = None

    model_config = ConfigDict(from_attributes=True)


class SettingsPayload(BaseModel):
    performance_mode: bool
    performanceMode: bool
    l2_auto_bypass: bool
    l2AutoBypass: bool
    session_timeout: int
    sessionTimeout: int
    lockout_threshold: int
    lockoutThreshold: int
    alerting_enabled: bool
    alertingEnabled: bool

    model_config = ConfigDict(from_attributes=True)


async def _read_settings_dict(db: AsyncSession) -> dict[str, Any]:
    stmt = select(AppSetting)
    res = await db.execute(stmt)
    rows = res.scalars().all()
    kv = {r.setting_key: r.setting_value for r in rows}

    perf_mode = False
    if "performance_mode" in kv:
        perf_mode = kv["performance_mode"].strip().lower() in (
            "true",
            "1",
            "redis",
            "yes",
        )
    elif hasattr(app_cfg, "redis"):
        perf_mode = bool(getattr(app_cfg.redis, "performance_mode", False))

    l2_bypass = True
    if "l2_auto_bypass" in kv:
        l2_bypass = kv["l2_auto_bypass"].strip().lower() in ("true", "1", "yes")

    session_timeout = 120
    if "session_timeout" in kv:
        try:
            session_timeout = int(kv["session_timeout"])
        except ValueError:
            pass

    lockout_threshold = 5
    if "lockout_threshold" in kv:
        try:
            lockout_threshold = int(kv["lockout_threshold"])
        except ValueError:
            pass

    alerting_enabled = True
    if "alerting_enabled" in kv:
        alerting_enabled = kv["alerting_enabled"].strip().lower() in ("true", "1", "yes")

    return {
        "performance_mode": perf_mode,
        "performanceMode": perf_mode,
        "l2_auto_bypass": l2_bypass,
        "l2AutoBypass": l2_bypass,
        "session_timeout": session_timeout,
        "sessionTimeout": session_timeout,
        "lockout_threshold": lockout_threshold,
        "lockoutThreshold": lockout_threshold,
        "alerting_enabled": alerting_enabled,
        "alertingEnabled": alerting_enabled,
    }


async def _upsert_setting(db: AsyncSession, key: str, value: str) -> None:
    stmt = select(AppSetting).where(AppSetting.setting_key == key)
    res = await db.execute(stmt)
    setting = res.scalar_one_or_none()
    if setting is not None:
        setting.setting_value = value
    else:
        setting = AppSetting(setting_key=key, setting_value=value)
        db.add(setting)
    await db.flush()


@router.get("", response_model=APIResponse)
async def get_settings(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    settings_data = await _read_settings_dict(db)
    return APIResponse.success(data=SettingsPayload(**settings_data))


@router.patch("", response_model=APIResponse)
async def update_settings(
    payload: SettingsUpdate,
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    perf_mode_val = payload.performance_mode
    if perf_mode_val is None and payload.performanceMode is not None:
        perf_mode_val = payload.performanceMode

    l2_bypass_val = payload.l2_auto_bypass
    if l2_bypass_val is None and payload.l2AutoBypass is not None:
        l2_bypass_val = payload.l2AutoBypass

    session_timeout_val = payload.session_timeout
    if session_timeout_val is None and payload.sessionTimeout is not None:
        session_timeout_val = payload.sessionTimeout

    lockout_val = payload.lockout_threshold
    if lockout_val is None and payload.lockoutThreshold is not None:
        lockout_val = payload.lockoutThreshold

    alerting_val = payload.alerting_enabled
    if alerting_val is None and payload.alertingEnabled is not None:
        alerting_val = payload.alertingEnabled

    reinit_driver = False

    if perf_mode_val is not None:
        await _upsert_setting(
            db, "performance_mode", "true" if perf_mode_val else "false"
        )
        reinit_driver = True

    if l2_bypass_val is not None:
        await _upsert_setting(
            db, "l2_auto_bypass", "true" if l2_bypass_val else "false"
        )

    if session_timeout_val is not None:
        await _upsert_setting(db, "session_timeout", str(session_timeout_val))

    if lockout_val is not None:
        await _upsert_setting(db, "lockout_threshold", str(lockout_val))

    if alerting_val is not None:
        await _upsert_setting(db, "alerting_enabled", "true" if alerting_val else "false")

    await db.commit()

    if reinit_driver:
        logger.info("performance_mode updated. Re-initializing storage driver manager...")
        try:
            await driver_manager.initialize()
        except Exception as e:
            logger.error("Failed to reinitialize driver manager: %s", e)

    updated_data = await _read_settings_dict(db)
    return APIResponse.success(data=SettingsPayload(**updated_data))
