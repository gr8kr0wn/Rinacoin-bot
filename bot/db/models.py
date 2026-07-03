import uuid
from datetime import datetime
from sqlalchemy import (
    Column, Uuid, BigInteger, Text, Integer, Boolean,
    DateTime, ForeignKey, UniqueConstraint, Index, JSON,
)
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    telegram_id = Column(BigInteger, unique=True, nullable=False)
    username = Column(Text, nullable=True)
    wallet_address = Column(Text, unique=True, nullable=True)
    level = Column(Integer, nullable=False, default=1)
    points = Column(BigInteger, nullable=False, default=0)
    lifetime_points = Column(BigInteger, nullable=False, default=0)
    daily_streak = Column(Integer, nullable=False, default=0)
    last_daily_at = Column(DateTime(timezone=True), nullable=True)
    joined_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_seen_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    is_admin = Column(Boolean, nullable=False, default=False)
    is_banned = Column(Boolean, nullable=False, default=False)
    referred_by = Column(Uuid, ForeignKey("users.id"), nullable=True)

    referrals_made = relationship("Referral", foreign_keys="Referral.referrer_id", back_populates="referrer")
    referral_received = relationship("Referral", foreign_keys="Referral.referred_id", back_populates="referred", uselist=False)
    activity_logs = relationship("ActivityLog", back_populates="user")
    achievements = relationship("UserAchievement", back_populates="user")
    ai_logs = relationship("AiMessageLog", back_populates="user")
    admin_actions = relationship("AdminAction", foreign_keys="AdminAction.admin_user_id", back_populates="admin")

    __table_args__ = (
        Index("points_idx", points.desc()),
        Index("referred_by_idx", referred_by),
    )


class ActivityLog(Base):
    __tablename__ = "activity_log"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id"), nullable=False)
    event_type = Column(Text, nullable=False)
    points_delta = Column(Integer, nullable=False)
    idempotency_key = Column(Text, unique=True, nullable=False)
    metadata_ = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    user = relationship("User", back_populates="activity_logs")

    __table_args__ = (
        Index("user_id_created_at_idx", user_id, created_at.desc()),
    )


class Referral(Base):
    __tablename__ = "referrals"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    referrer_id = Column(Uuid, ForeignKey("users.id"), nullable=False)
    referred_id = Column(Uuid, ForeignKey("users.id"), unique=True, nullable=False)
    status = Column(Text, nullable=False, default="pending")
    qualified_at = Column(DateTime(timezone=True), nullable=True)
    rewarded_at = Column(DateTime(timezone=True), nullable=True)
    rejection_reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    referrer = relationship("User", foreign_keys=[referrer_id], back_populates="referrals_made")
    referred = relationship("User", foreign_keys=[referred_id], back_populates="referral_received")


class PetState(Base):
    __tablename__ = "pet_state"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    community_id = Column(BigInteger, unique=True, nullable=False)
    mood = Column(Text, nullable=False, default="happy")
    mood_score = Column(Integer, nullable=False, default=0)
    energy = Column(Integer, nullable=False, default=50)
    last_interacted_at = Column(DateTime(timezone=True), nullable=True)
    last_mood_change_at = Column(DateTime(timezone=True), nullable=True)
    stage = Column(Text, nullable=False, default="egg")
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Achievement(Base):
    __tablename__ = "achievements"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    code = Column(Text, unique=True, nullable=False)
    name = Column(Text, nullable=False)
    description = Column(Text, nullable=False)
    points_reward = Column(Integer, nullable=False, default=0)
    icon = Column(Text, nullable=True)


class UserAchievement(Base):
    __tablename__ = "user_achievements"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id"), nullable=False)
    achievement_id = Column(Uuid, ForeignKey("achievements.id"), nullable=False)
    unlocked_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    user = relationship("User", back_populates="achievements")

    __table_args__ = (
        UniqueConstraint("user_id", "achievement_id", name="user_achievement_uniq"),
    )


class AiMessageLog(Base):
    __tablename__ = "ai_message_log"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id"), nullable=True)
    prompt_type = Column(Text, nullable=False)
    input_context = Column(JSON, nullable=True)
    output_text = Column(Text, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    user = relationship("User", back_populates="ai_logs")


class AdminAction(Base):
    __tablename__ = "admin_actions"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    admin_user_id = Column(Uuid, ForeignKey("users.id"), nullable=False)
    action_type = Column(Text, nullable=False)
    target_user_id = Column(Uuid, ForeignKey("users.id"), nullable=True)
    details = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    admin = relationship("User", foreign_keys=[admin_user_id], back_populates="admin_actions")


class JobRun(Base):
    __tablename__ = "job_runs"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    job_name = Column(Text, nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    finished_at = Column(DateTime(timezone=True), nullable=True)
    error = Column(Text, nullable=True)
