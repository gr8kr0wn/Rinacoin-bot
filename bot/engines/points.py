import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update, desc, and_, text, Integer, func as sa_func
from sqlalchemy.dialects.postgresql import insert as pg_insert

from sqlalchemy.ext.asyncio import async_sessionmaker

from bot.db.database import get_async_session
from bot.db.models import User, ActivityLog


POINT_SOURCES = {
    "daily_claim": 10,
    "referral_bonus": 50,
    "achievement_reward": (5, 100),
    "message_activity": 1,
    "manual_admin_grant": None,
}

DAILY_MESSAGE_CAP = 20
STREAK_BONUS_CAP = 50


@dataclass
class AwardResult:
    applied: bool
    reason: str | None = None
    new_points: int | None = None
    new_level: int | None = None
    streak: int | None = None
    bonus: int | None = None


@dataclass
class LeaderboardEntry:
    user_id: str
    username: str | None
    points: int
    level: int
    rank: int


def compute_level(lifetime_points: int) -> int:
    return int(math.isqrt(lifetime_points // 100)) + 1


_session_maker: async_sessionmaker | None = None


def _get_session_maker():
    global _session_maker
    if _session_maker is None:
        _session_maker = get_async_session()
    return _session_maker


class PointsEngine:
    async def award_points(
        self,
        user_id: str,
        amount: int,
        reason: str,
        idempotency_key: str,
        meta: dict | None = None,
        community_id: int | None = None,
    ) -> AwardResult:
        async with _get_session_maker()() as session:
            async with session.begin():
                stmt = (
                    pg_insert(ActivityLog)
                    .values(
                        user_id=user_id,
                        event_type=reason,
                        points_delta=amount,
                        idempotency_key=idempotency_key,
                        metadata_=meta,
                    )
                    .on_conflict_do_nothing(index_elements=["idempotency_key"])
                    .returning(ActivityLog.id)
                )
                result = await session.execute(stmt)
                inserted_id = result.scalar_one_or_none()

                if inserted_id is None:
                    return AwardResult(applied=False, reason="duplicate")

                user = await session.get(User, user_id)
                if user is None:
                    return AwardResult(applied=False, reason="user_not_found")

                new_points = (user.points or 0) + amount
                lifetime_delta = max(amount, 0)
                new_lifetime = (user.lifetime_points or 0) + lifetime_delta
                new_level = compute_level(new_lifetime)

                user.points = new_points
                user.lifetime_points = new_lifetime
                if new_level != user.level:
                    user.level = new_level

                if reason != "referral_bonus":
                    from bot.engines.referral import referral_engine
                    await referral_engine.on_user_activity(user_id, session_override=session)

            if community_id is not None and reason != "referral_bonus":
                from bot.engines.pet import pet_engine, PetTriggerEvent
                await pet_engine.on_event(community_id, PetTriggerEvent(type="points_awarded"))

            return AwardResult(
                applied=True,
                new_points=new_points,
                new_level=new_level,
            )

    async def get_balance(self, user_id: str) -> int:
        async with _get_session_maker()() as session:
            user = await session.get(User, user_id)
            return user.points if user else 0

    async def get_leaderboard(self, limit: int = 10) -> list[LeaderboardEntry]:
        async with _get_session_maker()() as session:
            result = await session.execute(
                select(User)
                .where(User.is_banned == False)
                .order_by(User.points.desc())
                .limit(limit)
            )
            users = result.scalars().all()
            return [
                LeaderboardEntry(
                    user_id=str(u.id),
                    username=u.username,
                    points=u.points,
                    level=u.level,
                    rank=i + 1,
                )
                for i, u in enumerate(users)
            ]

    async def claim_daily(self, user_id: str, community_id: int | None = None) -> AwardResult:
        async with _get_session_maker()() as session:
            async with session.begin():
                user = await session.get(User, user_id)
                if user is None:
                    return AwardResult(applied=False, reason="user_not_found")

                now = datetime.now(timezone.utc)
                today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
                yesterday_start = today_start - timedelta(days=1)

                last_daily = user.last_daily_at

                if last_daily and last_daily >= today_start:
                    return AwardResult(applied=False, reason="already_claimed")

                if last_daily is None or last_daily < yesterday_start:
                    new_streak = 1
                else:
                    new_streak = (user.daily_streak or 0) + 1

                bonus = min(new_streak * 2, STREAK_BONUS_CAP)
                total_points = 10 + bonus

                idempotency_key = f"daily:{user_id}:{today_start.date()}"
                already_processed = await _idempotency_check(session, idempotency_key)
                if already_processed:
                    return AwardResult(applied=False, reason="duplicate")

                await session.execute(
                    pg_insert(ActivityLog)
                    .values(
                        user_id=user_id,
                        event_type="daily_claim",
                        points_delta=total_points,
                        idempotency_key=idempotency_key,
                        metadata_={"streak": new_streak, "bonus": bonus},
                    )
                    .on_conflict_do_nothing(index_elements=["idempotency_key"])
                )

                user.points = (user.points or 0) + total_points
                lifetime_delta = max(total_points, 0)
                user.lifetime_points = (user.lifetime_points or 0) + lifetime_delta
                new_level = compute_level(user.lifetime_points)
                if new_level != user.level:
                    user.level = new_level
                user.daily_streak = new_streak
                user.last_daily_at = now

                from bot.engines.referral import referral_engine
                await referral_engine.on_user_activity(user_id, session_override=session)

            if community_id is not None:
                from bot.engines.pet import pet_engine, PetTriggerEvent
                await pet_engine.on_event(community_id, PetTriggerEvent(type="points_awarded"))

            return AwardResult(
                applied=True,
                new_points=user.points if hasattr(user, "points") else 0,
                new_level=new_level,
                streak=new_streak,
                bonus=bonus,
            )

    async def snapshot_weekly(self):
        return {"ok": True, "note": "placeholder — weekly snapshot not yet implemented"}

    async def check_message_activity(
        self,
        user_id: str,
        message_text: str,
        telegram_message_id: int,
        community_id: int | None = None,
    ) -> AwardResult:
        if len(message_text.strip()) < 5:
            return AwardResult(applied=False, reason="too_short")

        async with _get_session_maker()() as session:
            async with session.begin():
                today_start = datetime.now(timezone.utc).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )

                daily_count = await session.execute(
                    select(sa_func.count())
                    .select_from(ActivityLog)
                    .where(
                        and_(
                            ActivityLog.user_id == user_id,
                            ActivityLog.event_type == "message_activity",
                            ActivityLog.created_at >= today_start,
                        )
                    )
                )
                if daily_count.scalar() or 0 >= DAILY_MESSAGE_CAP:
                    return AwardResult(applied=False, reason="daily_cap_reached")

                recent = await session.execute(
                    select(ActivityLog.metadata_)
                    .where(
                        and_(
                            ActivityLog.user_id == user_id,
                            ActivityLog.event_type == "message_activity",
                        )
                    )
                    .order_by(ActivityLog.created_at.desc())
                    .limit(3)
                )
                recent_texts = []
                for row in recent.scalars().all():
                    if row and "text" in row:
                        recent_texts.append(row["text"])

                if message_text.strip() in recent_texts:
                    return AwardResult(applied=False, reason="duplicate_message")

                last_msg = (
                    await session.execute(
                        select(ActivityLog.created_at)
                        .where(
                            and_(
                                ActivityLog.user_id == user_id,
                                ActivityLog.event_type == "message_activity",
                            )
                        )
                        .order_by(ActivityLog.created_at.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()

                if last_msg:
                    elapsed = (datetime.now(timezone.utc) - last_msg).total_seconds()
                    if elapsed < 3:
                        return AwardResult(applied=False, reason="rate_limited")

            return await self.award_points(
                user_id=user_id,
                amount=1,
                reason="message_activity",
                idempotency_key=f"msg:{telegram_message_id}",
                meta={"text": message_text.strip()},
                community_id=community_id,
            )


async def _idempotency_check(session, key: str) -> bool:
    result = await session.execute(
        select(ActivityLog.id).where(ActivityLog.idempotency_key == key)
    )
    return result.scalar_one_or_none() is not None


points_engine = PointsEngine()
