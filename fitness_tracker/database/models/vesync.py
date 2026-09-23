"""Measurements imported from the VeSync scale."""

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, Float, Integer, String
from sqlalchemy.sql import func

from fitness_tracker.database.models.base import BaseModel


class VeSyncWeighIn(BaseModel):
    """One measurement from the account owner's scale profile."""

    __tablename__: str = __qualname__

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_key = Column(String(64), nullable=False, unique=True)
    measured_at = Column(DateTime(timezone=True), nullable=False, index=True)
    weight_g = Column(Integer, nullable=False)
    impedance_ohms = Column(Float)
    body_fat_pct = Column(Float)
    is_manual_input = Column(Boolean, nullable=False, default=False)
    imported_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (CheckConstraint("weight_g > 0", name="ck_vesync_weigh_in_weight_positive"),)
