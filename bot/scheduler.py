from datetime import datetime, timezone
from uuid import uuid4

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger
from sqlalchemy import select

from bot.db.database import get_async_session
from bot.db.models import JobRun, PetState as PetStateDB

schedule = AsyncIOScheduler()


async def _get_all_community_ids() -> list[int]:
    async with get_async_session()() as session:
        result = await session.execute(
            select(PetStateDB.community_id).distinct()
        )
        return [row[0] for row in result.all()]


async def _log_and_run(job_name: str, fn):
    run_id = uuid4()
    started = datetime.now(timezone.utc)

    async with get_async_session()() as session:
        async with session.begin():
            session.add(JobRun(id=run_id, job_name=job_name, started_at=started))

    try:
        await fn()
        finished = datetime.now(timezone.utc)
        async with get_async_session()() as session:
            async with session.begin():
                log = await session.get(JobRun, run_id)
                if log:
                    log.finished_at = finished
        logger.info(f"job {job_name}: ok")
    except Exception as e:
        finished = datetime.now(timezone.utc)
        async with get_async_session()() as session:
            async with session.begin():
                log = await session.get(JobRun, run_id)
                if log:
                    log.finished_at = finished
                    log.error = str(e)
        logger.error(f"job {job_name}: {e}")


# ── Job implementations ─────────────────────────────────────────────────────

async def _expire_stale():
    from bot.engines.referral import referral_engine
    count = await referral_engine.expire_stale_referrals()
    logger.info(f"expired {count} stale referrals")


async def _twitter_stub():
    logger.info("twitter_search: not yet implemented")


async def _decay_pets():
    communities = await _get_all_community_ids()
    from bot.engines.pet import pet_engine
    for cid in communities:
        await pet_engine.decay(cid)


async def _weekly_snap():
    from bot.engines.points import points_engine
    await points_engine.snapshot_weekly()


async def _check_lonely():
    from bot.engines.pet import pet_engine
    from bot.ai.brain import ai_brain
    communities = await _get_all_community_ids()
    for cid in communities:
        lonely, msg = await pet_engine.check_loneliness(cid)
        if lonely:
            reply = await ai_brain.generate_reply("lonely_ping", hours=6)
            logger.info(f"lonely_ping community={cid}: {reply}")


# ── Public job wrappers (with logging) ──────────────────────────────────────

async def expire_stale_referrals():
    await _log_and_run("expire_stale_referrals", _expire_stale)


async def twitter_search():
    await _log_and_run("twitter_search", _twitter_stub)


async def pet_decay():
    await _log_and_run("pet_decay", _decay_pets)


async def weekly_snapshot():
    await _log_and_run("weekly_snapshot", _weekly_snap)


async def loneliness_check():
    await _log_and_run("loneliness_check", _check_lonely)


# ── Registration ────────────────────────────────────────────────────────────

def setup_scheduler():
    schedule.add_job(
        expire_stale_referrals,
        CronTrigger(hour=0, minute=0),
        id="expire_stale_referrals",
        replace_existing=True,
    )
    schedule.add_job(
        twitter_search,
        CronTrigger(minute="*/10"),
        id="twitter_search",
        replace_existing=True,
    )
    schedule.add_job(
        pet_decay,
        CronTrigger(minute=0),
        id="pet_decay",
        replace_existing=True,
    )
    schedule.add_job(
        weekly_snapshot,
        CronTrigger(day_of_week="sun", hour=0, minute=0),
        id="weekly_snapshot",
        replace_existing=True,
    )
    schedule.add_job(
        loneliness_check,
        CronTrigger(minute="*/30"),
        id="loneliness_check",
        replace_existing=True,
    )
    logger.info("Scheduler configured with 5 jobs")
