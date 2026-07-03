"""Tests for Pet Engine — mood resolution, stage progression, trigger effects."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from bot.engines.pet import (
    PetEngine,
    PetState,
    PetTriggerEvent,
    PetEventResult,
    resolve_mood,
    compute_stage,
)


# ── resolve_mood (pure function, no DB) ─────────────────────────────────────

def test_energy_below_15_is_sleepy():
    assert resolve_mood(mood_score=50, energy=14) == "sleepy"
    assert resolve_mood(mood_score=-50, energy=0) == "sleepy"
    assert resolve_mood(mood_score=0, energy=14) == "sleepy"


def test_sleepy_takes_priority_over_all():
    assert resolve_mood(mood_score=80, energy=14) == "sleepy"


def test_no_interaction_6h_is_lonely():
    now = datetime.now(timezone.utc)
    old = now - timedelta(hours=7)
    assert (
        resolve_mood(mood_score=50, energy=80, last_interacted_at=old, now=now)
        == "lonely"
    )


def test_lonely_takes_priority_over_excited():
    now = datetime.now(timezone.utc)
    old = now - timedelta(hours=6, minutes=1)
    result = resolve_mood(
        mood_score=70, energy=80, last_interacted_at=old, now=now
    )
    assert result == "lonely"


def test_never_interacted_is_lonely():
    assert resolve_mood(mood_score=50, energy=80) == "lonely"


def test_excited_requires_high_score_and_energy():
    now = datetime.now(timezone.utc)
    recent = now - timedelta(minutes=5)
    assert (
        resolve_mood(mood_score=60, energy=60, last_interacted_at=recent, now=now)
        == "excited"
    )
    assert (
        resolve_mood(mood_score=59, energy=60, last_interacted_at=recent, now=now)
        != "excited"
    )
    assert (
        resolve_mood(mood_score=60, energy=59, last_interacted_at=recent, now=now)
        != "excited"
    )


def test_happy_at_mood_score_20_plus():
    now = datetime.now(timezone.utc)
    recent = now - timedelta(minutes=5)
    assert (
        resolve_mood(mood_score=20, energy=50, last_interacted_at=recent, now=now)
        == "happy"
    )
    assert (
        resolve_mood(mood_score=59, energy=50, last_interacted_at=recent, now=now)
        == "happy"
    )


def test_happy_takes_priority_over_playful_at_20():
    """mood_score >= 20 is checked before playful, so score=20 with energy=70 is happy."""
    now = datetime.now(timezone.utc)
    recent = now - timedelta(minutes=5)
    assert (
        resolve_mood(mood_score=20, energy=70, last_interacted_at=recent, now=now)
        == "happy"
    )


def test_sad_at_mood_score_minus_40():
    now = datetime.now(timezone.utc)
    recent = now - timedelta(minutes=5)
    assert (
        resolve_mood(mood_score=-40, energy=50, last_interacted_at=recent, now=now)
        == "sad"
    )
    assert (
        resolve_mood(mood_score=-50, energy=50, last_interacted_at=recent, now=now)
        == "sad"
    )
    assert (
        resolve_mood(mood_score=-39, energy=50, last_interacted_at=recent, now=now)
        != "sad"
    )


def test_playful_at_high_energy_mid_score():
    now = datetime.now(timezone.utc)
    recent = now - timedelta(minutes=5)
    for ms in range(-20, 20):
        assert (
            resolve_mood(mood_score=ms, energy=70, last_interacted_at=recent, now=now)
            == "playful"
        ), f"expected playful at mood_score={ms}, energy=70"
    assert (
        resolve_mood(mood_score=0, energy=69, last_interacted_at=recent, now=now)
        != "playful"
    )
    assert (
        resolve_mood(mood_score=21, energy=70, last_interacted_at=recent, now=now)
        != "playful"
    )


def test_curious_with_question_or_mystery_event():
    now = datetime.now(timezone.utc)
    recent = now - timedelta(minutes=5)
    assert (
        resolve_mood(
            mood_score=0,
            energy=50,
            last_interacted_at=recent,
            last_event_type="question",
            now=now,
        )
        == "curious"
    )
    assert (
        resolve_mood(
            mood_score=0,
            energy=50,
            last_interacted_at=recent,
            last_event_type="mystery",
            now=now,
        )
        == "curious"
    )


def test_curious_not_triggered_by_other_events():
    now = datetime.now(timezone.utc)
    recent = now - timedelta(minutes=5)
    assert (
        resolve_mood(
            mood_score=0,
            energy=50,
            last_interacted_at=recent,
            last_event_type="points_awarded",
            now=now,
        )
        != "curious"
    )


def test_hungry_at_low_energy():
    now = datetime.now(timezone.utc)
    recent = now - timedelta(minutes=5)
    for e in range(15, 40):
        assert (
            resolve_mood(mood_score=-10, energy=e, last_interacted_at=recent, now=now)
            == "hungry"
        ), f"expected hungry at energy={e}"
    assert (
        resolve_mood(mood_score=-10, energy=14, last_interacted_at=recent, now=now)
        == "sleepy"
    )
    assert (
        resolve_mood(mood_score=-10, energy=40, last_interacted_at=recent, now=now)
        != "hungry"
    )


def test_default_is_happy():
    now = datetime.now(timezone.utc)
    recent = now - timedelta(minutes=5)
    assert (
        resolve_mood(mood_score=10, energy=50, last_interacted_at=recent, now=now)
        == "happy"
    )


# ── compute_stage (pure function) ──────────────────────────────────────────

def test_stage_egg_below_1k():
    assert compute_stage(0) == "egg"
    assert compute_stage(999) == "egg"


def test_stage_hatchling_1k_to_10k():
    assert compute_stage(1_000) == "hatchling"
    assert compute_stage(9_999) == "hatchling"


def test_stage_juvenile_10k_to_50k():
    assert compute_stage(10_000) == "juvenile"
    assert compute_stage(49_999) == "juvenile"


def test_stage_adult_50k_to_200k():
    assert compute_stage(50_000) == "adult"
    assert compute_stage(199_999) == "adult"


def test_stage_elder_200k_plus():
    assert compute_stage(200_000) == "elder"
    assert compute_stage(1_000_000) == "elder"


# ── _apply_trigger (pure logic, no DB) ─────────────────────────────────────

@pytest.fixture
def state():
    return PetState(energy=50, mood_score=0)


def test_points_awarded_trigger(state):
    PetEngine._apply_trigger(None, state, PetTriggerEvent(type="points_awarded"))
    assert state.energy == 52
    assert state.mood_score == 1


def test_pet_interaction_trigger(state):
    PetEngine._apply_trigger(None, state, PetTriggerEvent(type="pet_interaction"))
    assert state.energy == 60
    assert state.mood_score == 3


def test_streak_broken_trigger(state):
    PetEngine._apply_trigger(None, state, PetTriggerEvent(type="streak_broken"))
    assert state.energy == 50
    assert state.mood_score == -2


def test_achievement_unlocked_trigger(state):
    PetEngine._apply_trigger(None, state, PetTriggerEvent(type="achievement_unlocked"))
    assert state.energy == 50
    assert state.mood_score == 5


def test_decay_trigger(state):
    PetEngine._apply_trigger(None, state, PetTriggerEvent(type="decay"))
    assert state.energy == 45
    assert state.mood_score == 0


def test_energy_caps_at_100():
    s = PetState(energy=99, mood_score=0)
    PetEngine._apply_trigger(None, s, PetTriggerEvent(type="pet_interaction"))
    assert s.energy == 100


def test_energy_floor_at_0():
    s = PetState(energy=2, mood_score=0)
    PetEngine._apply_trigger(None, s, PetTriggerEvent(type="decay"))
    assert s.energy == 0


def test_mood_score_caps():
    s = PetState(energy=50, mood_score=99)
    PetEngine._apply_trigger(None, s, PetTriggerEvent(type="pet_interaction"))
    assert s.mood_score == 100

    s = PetState(energy=50, mood_score=-99)
    PetEngine._apply_trigger(None, s, PetTriggerEvent(type="streak_broken"))
    assert s.mood_score == -100


# ── on_event integration (mocked DB) ────────────────────────────────────────

@pytest.fixture
def engine():
    return PetEngine()


def _make_mock_state(**overrides) -> MagicMock:
    defaults = dict(
        mood="happy", stage="egg", energy=50, mood_score=0,
        last_interacted_at=None, last_mood_change_at=None,
        updated_at=None,
    )
    defaults.update(overrides)
    row = MagicMock()
    for k, v in defaults.items():
        setattr(row, k, v)
    return row


@pytest.mark.asyncio
async def test_on_event_first_time_no_state(engine):
    with patch.object(engine, "_load_state", AsyncMock(return_value=None)):
        with patch.object(engine, "_save_state", AsyncMock()):
            with patch.object(engine, "_get_total_lifetime", AsyncMock(return_value=0)):
                result = await engine.on_event(-100, PetTriggerEvent(type="points_awarded"))

    assert isinstance(result, PetEventResult)
    assert result.energy == 52
    assert result.mood_score == 1
    assert result.mood in ("hungry", "sleepy", "playful", "curious", "lonely", "excited", "sad", "happy")


@pytest.mark.asyncio
async def test_on_event_excited_mood(engine):
    now = datetime.now(timezone.utc)
    existing = _make_mock_state(
        mood="happy", stage="hatchling", energy=70, mood_score=65,
        last_interacted_at=now - timedelta(minutes=5),
        last_mood_change_at=now - timedelta(hours=2),
        updated_at=now - timedelta(minutes=10),
    )

    with patch.object(engine, "_load_state", AsyncMock(return_value=existing)):
        with patch.object(engine, "_save_state", AsyncMock()):
            with patch.object(engine, "_get_total_lifetime", AsyncMock(return_value=5_000)):
                result = await engine.on_event(-100, PetTriggerEvent(type="points_awarded"))

    assert result.mood == "excited"
    assert result.stage == "hatchling"
    assert result.energy == 72
    assert result.mood_score == 66
