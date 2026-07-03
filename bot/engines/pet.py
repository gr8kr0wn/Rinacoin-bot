from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import async_sessionmaker

from bot.db.database import get_async_session
from bot.db.models import PetState as PetStateDB, User

Mood = Literal["hungry", "happy", "sleepy", "playful", "curious", "lonely", "excited", "sad"]
Stage = Literal["kitten", "juvenile", "adult", "senior", "elder"]


@dataclass
class PetState:
    mood: Mood = "happy"
    stage: Stage = "egg"
    energy: int = 50
    mood_score: int = 0
    last_interacted_at: datetime | None = None
    last_mood_change_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class PetTriggerEvent:
    type: str
    metadata: dict | None = None


@dataclass
class PetEventResult:
    mood: Mood
    stage: Stage
    energy: int
    mood_score: int
    mood_changed: bool
    stage_changed: bool
    should_announce: bool


def resolve_mood(
    mood_score: int,
    energy: int,
    last_interacted_at: datetime | None = None,
    last_event_type: str | None = None,
    now: datetime | None = None,
) -> Mood:
    now = now or datetime.now(timezone.utc)

    if energy < 15:
        return "sleepy"
    if last_interacted_at is None or (now - last_interacted_at) > timedelta(hours=6):
        return "lonely"
    if mood_score >= 60 and energy >= 60:
        return "excited"
    if mood_score >= 20:
        return "happy"
    if mood_score <= -40:
        return "sad"
    if energy >= 70 and -20 <= mood_score <= 20:
        return "playful"
    if last_event_type in ("question", "mystery"):
        return "curious"
    if energy < 40:
        return "hungry"
    return "happy"


def compute_stage(total_lifetime_points: int) -> Stage:
    if total_lifetime_points >= 50_000:
        return "elder"
    if total_lifetime_points >= 10_000:
        return "senior"
    if total_lifetime_points >= 2_000:
        return "adult"
    if total_lifetime_points >= 500:
        return "juvenile"
    return "kitten"


_session_maker: async_sessionmaker | None = None


def _get_session_maker():
    global _session_maker
    if _session_maker is None:
        _session_maker = get_async_session()
    return _session_maker


class PetEngine:
    def _apply_trigger(self, state: PetState, event: PetTriggerEvent) -> None:
        if event.type == "points_awarded":
            state.energy = min(state.energy + 2, 100)
            state.mood_score = max(-100, min(state.mood_score + 1, 100))
        elif event.type == "pet_interaction":
            state.energy = min(state.energy + 10, 100)
            state.mood_score = max(-100, min(state.mood_score + 3, 100))
        elif event.type == "streak_broken":
            state.mood_score = max(-100, min(state.mood_score - 2, 100))
        elif event.type == "achievement_unlocked":
            state.mood_score = max(-100, min(state.mood_score + 5, 100))
        elif event.type == "decay":
            state.energy = max(0, state.energy - 5)

    async def _load_state(self, community_id: int) -> PetState | None:
        async with _get_session_maker()() as session:
            row = await session.execute(
                select(PetStateDB).where(PetStateDB.community_id == community_id)
            )
            db = row.scalar_one_or_none()
            if db is None:
                return None
            return PetState(
                mood=db.mood,
                stage=db.stage,
                energy=db.energy,
                mood_score=db.mood_score,
                last_interacted_at=db.last_interacted_at,
                last_mood_change_at=db.last_mood_change_at,
                updated_at=db.updated_at,
            )

    async def _save_state(self, community_id: int, state: PetState) -> None:
        async with _get_session_maker()() as session:
            async with session.begin():
                row = await session.execute(
                    select(PetStateDB).where(PetStateDB.community_id == community_id)
                )
                db = row.scalar_one_or_none()
                if db is None:
                    db = PetStateDB(community_id=community_id)
                    session.add(db)
                db.mood = state.mood
                db.stage = state.stage
                db.energy = state.energy
                db.mood_score = state.mood_score
                db.last_interacted_at = state.last_interacted_at
                db.last_mood_change_at = state.last_mood_change_at
                db.updated_at = datetime.now(timezone.utc)

    async def _get_total_lifetime(self) -> int:
        async with _get_session_maker()() as session:
            result = await session.execute(
                select(sa_func.coalesce(sa_func.sum(User.lifetime_points), 0))
            )
            return result.scalar() or 0

    async def get_state(self, community_id: int) -> PetState:
        state = await self._load_state(community_id)
        if state is None:
            state = PetState()
            await self._save_state(community_id, state)
        return state

    async def on_event(self, community_id: int, event: PetTriggerEvent) -> PetEventResult:
        state = await self._load_state(community_id) or PetState()
        now = datetime.now(timezone.utc)
        old_mood = state.mood
        old_stage = state.stage

        self._apply_trigger(state, event)
        state.last_interacted_at = now

        total = await self._get_total_lifetime()
        state.stage = compute_stage(total)
        stage_changed = state.stage != old_stage

        should_evaluate = (
            state.updated_at is None
            or (now - state.updated_at).total_seconds() >= 60
        )

        mood_changed = False
        should_announce = False

        if should_evaluate:
            new_mood = resolve_mood(
                mood_score=state.mood_score,
                energy=state.energy,
                last_interacted_at=state.last_interacted_at,
                last_event_type=event.metadata.get("type") if event.metadata else None,
                now=now,
            )
            if new_mood != old_mood:
                mood_changed = True
                if (
                    state.last_mood_change_at is None
                    or (now - state.last_mood_change_at).total_seconds() >= 1800
                ):
                    should_announce = True
                state.last_mood_change_at = now
            state.mood = new_mood

        await self._save_state(community_id, state)

        return PetEventResult(
            mood=state.mood,
            stage=state.stage,
            energy=state.energy,
            mood_score=state.mood_score,
            mood_changed=mood_changed,
            stage_changed=stage_changed,
            should_announce=should_announce,
        )

    async def decay(self, community_id: int) -> PetEventResult:
        return await self.on_event(community_id, PetTriggerEvent(type="decay"))

    async def check_loneliness(self, community_id: int) -> tuple[bool, str | None]:
        state = await self._load_state(community_id)
        if state is None:
            return False, None
        now = datetime.now(timezone.utc)
        if state.last_interacted_at and (now - state.last_interacted_at) < timedelta(hours=6):
            return False, None
        if state.last_mood_change_at and (now - state.last_mood_change_at) < timedelta(hours=6):
            return False, None
        return True, f"*Rina meows sadly at the empty room*"


pet_engine = PetEngine()
