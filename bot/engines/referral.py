from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, and_
from sqlalchemy.dialects.postgresql import insert as pg_insert

from sqlalchemy.ext.asyncio import async_sessionmaker

from bot.db.database import get_async_session
from bot.db.models import User, Referral

QUALIFY_POINTS = 30
QUALIFY_HOURS = 24
REFERRAL_REWARD = 50
STALE_DAYS = 30
BOT_USERNAME = "RinaBot"


_session_maker: async_sessionmaker | None = None


def _get_session_maker():
    global _session_maker
    if _session_maker is None:
        _session_maker = get_async_session()
    return _session_maker


@dataclass
class ReferralStats:
    total_invited: int = 0
    pending: int = 0
    qualified: int = 0
    total_points_earned: int = 0
    shareable_link: str = ""


class ReferralEngine:
    async def register_referral(self, referrer_id: str, new_user_id: str) -> str | None:
        if referrer_id == new_user_id:
            return "self_referral"

        async with _get_session_maker()() as session:
            async with session.begin():
                referrer = await session.get(User, referrer_id)
                if referrer is None:
                    return "referrer_not_found"

                new_user = await session.get(User, new_user_id)
                if new_user is None:
                    return "new_user_not_found"

                if new_user.referred_by is not None:
                    return "already_referred"

                existing = await session.execute(
                    select(Referral).where(Referral.referred_id == new_user_id)
                )
                if existing.scalar_one_or_none() is not None:
                    return "duplicate"

                new_user.referred_by = referrer_id
                session.add(
                    Referral(
                        referrer_id=referrer_id,
                        referred_id=new_user_id,
                        status="pending",
                    )
                )
            return None

    async def on_user_activity(
        self,
        user_id: str,
        session_override=None,
    ) -> None:
        if session_override is not None:
            await self._check_and_reward(user_id, session_override)
            return

        async with _get_session_maker()() as session:
            async with session.begin():
                await self._check_and_reward(user_id, session)

    async def _check_and_reward(self, user_id: str, session) -> None:
        referral = await session.execute(
            select(Referral).where(
                and_(
                    Referral.referred_id == user_id,
                    Referral.status == "pending",
                )
            )
        )
        referral = referral.scalar_one_or_none()
        if referral is None:
            return

        user = await session.get(User, user_id)
        if user is None:
            return

        now = datetime.now(timezone.utc)
        hours_since_join = (now - user.joined_at).total_seconds() / 3600

        if user.lifetime_points >= QUALIFY_POINTS and hours_since_join >= QUALIFY_HOURS:
            referral.status = "qualified"
            referral.qualified_at = now
            session.add(referral)
            await session.flush()

            from bot.engines.points import points_engine

            result = await points_engine.award_points(
                user_id=str(referral.referrer_id),
                amount=REFERRAL_REWARD,
                reason="referral_bonus",
                idempotency_key=f"referral:{referral.id}:qualified",
                meta={"referred_user_id": user_id},
            )

            if result.applied:
                referral.status = "rewarded"
                referral.rewarded_at = now
                session.add(referral)

    async def get_referral_stats(self, user_id: str) -> ReferralStats:
        async with _get_session_maker()() as session:
            total = await session.execute(
                select(Referral).where(Referral.referrer_id == user_id)
            )
            all_refs = total.scalars().all()

            pending = sum(1 for r in all_refs if r.status == "pending")
            qualified = sum(1 for r in all_refs if r.status == "qualified")
            rewarded = sum(1 for r in all_refs if r.status == "rewarded")

            total_points = (
                await session.execute(
                    select(Referral)
                    .where(
                        and_(
                            Referral.referrer_id == user_id,
                            Referral.status == "rewarded",
                        )
                    )
                )
            ).scalars().all()

            return ReferralStats(
                total_invited=len(all_refs),
                pending=pending,
                qualified=qualified + rewarded,
                total_points_earned=len(total_points) * REFERRAL_REWARD,
                shareable_link=f"https://t.me/{BOT_USERNAME}?start=ref_{user_id}",
            )

    async def expire_stale_referrals(self) -> int:
        from bot.engines.points import points_engine

        cutoff = datetime.now(timezone.utc) - timedelta(days=STALE_DAYS)
        retry_cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
        async with _get_session_maker()() as session:
            async with session.begin():
                stale = await session.execute(
                    select(Referral).where(
                        and_(
                            Referral.status == "pending",
                            Referral.created_at < cutoff,
                        )
                    )
                )
                rows = stale.scalars().all()
                for r in rows:
                    r.status = "rejected"
                    r.rejection_reason = "inactive_30d"
                    session.add(r)

                stuck = await session.execute(
                    select(Referral).where(
                        and_(
                            Referral.status == "qualified",
                            Referral.qualified_at < retry_cutoff,
                        )
                    )
                )
                for r in stuck.scalars().all():
                    ref_user = await session.get(User, r.referred_id)
                    if ref_user and ref_user.lifetime_points >= QUALIFY_POINTS:
                        result = await points_engine.award_points(
                            user_id=str(r.referrer_id),
                            amount=REFERRAL_REWARD,
                            reason="referral_bonus",
                            idempotency_key=f"referral:{r.id}:qualified",
                            meta={"referred_user_id": str(r.referred_id)},
                        )
                        if result.applied:
                            r.status = "rewarded"
                            r.rewarded_at = datetime.now(timezone.utc)
                            session.add(r)
                    else:
                        r.status = "rejected"
                        r.rejection_reason = "inactive_30d"
                        session.add(r)

                return len(rows)

    async def ban_check(self, user_id: str) -> None:
        async with _get_session_maker()() as session:
            async with session.begin():
                referrals = await session.execute(
                    select(Referral).where(
                        and_(
                            Referral.referred_id == user_id,
                            Referral.status == "pending",
                        )
                    )
                )
                for ref in referrals.scalars().all():
                    ref.status = "rejected"
                    ref.rejection_reason = "banned"
                    session.add(ref)

    async def leave_check(self, user_id: str) -> None:
        async with _get_session_maker()() as session:
            async with session.begin():
                referrals = await session.execute(
                    select(Referral).where(
                        and_(
                            Referral.referred_id == user_id,
                            Referral.status == "pending",
                        )
                    )
                )
                for ref in referrals.scalars().all():
                    ref.status = "rejected"
                    ref.rejection_reason = "left_before_qualifying"
                    session.add(ref)


referral_engine = ReferralEngine()
