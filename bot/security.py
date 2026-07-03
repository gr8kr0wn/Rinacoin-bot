"""Security middleware: webhook verification, rate limiting, sybil detection."""

import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from uuid import uuid4

from loguru import logger
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from bot.config import settings
from bot.db.database import get_async_session
from bot.db.models import User, AdminAction, ActivityLog


def verify_webhook_secret(header: str | None) -> bool:
    expected = settings.telegram_webhook_secret
    if not expected:
        return True
    return header == expected


# ── Rate Limiter ────────────────────────────────────────────────────────────

class RateLimiter:
    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._buckets: dict[int, deque] = defaultdict(deque)

    def check(self, user_id: int) -> bool:
        now = time.monotonic()
        bucket = self._buckets[user_id]
        while bucket and bucket[0] < now - self.window_seconds:
            bucket.popleft()
        if len(bucket) >= self.max_requests:
            return False
        bucket.append(now)
        return True

    def reset(self, user_id: int):
        self._buckets.pop(user_id, None)


command_limiter = RateLimiter(max_requests=10, window_seconds=60)
ai_limiter = RateLimiter(max_requests=5, window_seconds=60)


def check_command_rate(user_id: int) -> bool:
    return command_limiter.check(user_id)


def check_ai_rate(user_id: int) -> bool:
    return ai_limiter.check(user_id)


# ── Sybil Detection ─────────────────────────────────────────────────────────

async def flag_suspicious_referral(referrer_id: str, referred_id: str):
    async with get_async_session()() as session:
        async with session.begin():
            now = datetime.now(timezone.utc)
            referred = await session.get(User, referred_id)
            referrer = await session.get(User, referrer_id)
            if not referred or not referrer:
                return

            flags = []

            signup_diff = abs((referred.joined_at - referrer.joined_at).total_seconds()) if referred.joined_at and referrer.joined_at else 9999
            if signup_diff < 60:
                flags.append("same_minute_signup")

            recent_refs_query = await session.execute(
                select(User)
                .where(User.referred_by == referrer.id)
                .order_by(User.joined_at.desc())
                .limit(5)
            )
            recent_refs = recent_refs_query.scalars().all()
            if len(recent_refs) >= 2:
                times = [r.joined_at for r in recent_refs if r.joined_at]
                if len(times) >= 2 and all(
                    abs((times[i] - times[i+1]).total_seconds()) < 30
                    for i in range(len(times) - 1)
                ):
                    flags.append("rapid_fire_referrals")

            msg_count = await session.execute(
                select(ActivityLog.id)
                .where(
                    ActivityLog.user_id == referred.id,
                    ActivityLog.event_type == "message_activity",
                )
                .limit(1)
            )
            if msg_count.scalar_one_or_none() is None and (referred.lifetime_points or 0) >= 30:
                flags.append("points_without_messages")

            if flags:
                action = AdminAction(
                    id=uuid4(),
                    admin_user_id=referrer.id,
                    action_type="sybil_flag",
                    target_user_id=referred.id,
                    details={"flags": flags},
                )
                session.add(action)
                logger.warning(f"Sybil flags for referral {referrer_id} -> {referred_id}: {flags}")


__all__ = [
    "verify_webhook_secret",
    "RateLimiter",
    "command_limiter", "ai_limiter",
    "check_command_rate", "check_ai_rate",
    "flag_suspicious_referral",
    "logger",
]
