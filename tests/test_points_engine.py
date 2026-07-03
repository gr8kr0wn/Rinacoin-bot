"""Tests for PointsEngine using mocked database."""

from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from bot.engines.points import PointsEngine, compute_level


@pytest.fixture
def engine():
    return PointsEngine()


@pytest.fixture
def mock_session():
    session = AsyncMock(spec=AsyncSession)

    begin_cm = MagicMock()
    begin_cm.__aenter__ = AsyncMock(return_value=session)
    begin_cm.__aexit__ = AsyncMock(return_value=None)
    session.begin.return_value = begin_cm

    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=session)
    session_cm.__aexit__ = AsyncMock(return_value=None)

    maker = MagicMock(return_value=session_cm)

    mock_result = MagicMock()
    session.execute.return_value = mock_result

    return maker, session


@pytest.mark.asyncio
async def test_award_points_applied(engine, mock_session):
    maker, session = mock_session
    session.execute.return_value.scalar_one_or_none.return_value = "new-id"
    session.get.return_value = MagicMock(
        points=100, lifetime_points=500, level=3, id="user-1"
    )

    with patch("bot.engines.points._get_session_maker", return_value=maker):
        result = await engine.award_points(
            user_id="user-1",
            amount=50,
            reason="referral_bonus",
            idempotency_key="ref:abc:qualified",
        )

    assert result.applied is True


@pytest.mark.asyncio
async def test_award_points_duplicate(engine, mock_session):
    maker, session = mock_session
    session.execute.return_value.scalar_one_or_none.return_value = None

    with patch("bot.engines.points._get_session_maker", return_value=maker):
        result = await engine.award_points(
            user_id="user-1",
            amount=10,
            reason="daily_claim",
            idempotency_key="daily:user-1:2026-07-02",
        )

    assert result.applied is False
    assert result.reason == "duplicate"


@pytest.mark.asyncio
async def test_award_points_user_not_found(engine, mock_session):
    maker, session = mock_session
    session.execute.return_value.scalar_one_or_none.return_value = "new-id"
    session.get.return_value = None

    with patch("bot.engines.points._get_session_maker", return_value=maker):
        result = await engine.award_points(
            user_id="nonexistent",
            amount=10,
            reason="daily_claim",
            idempotency_key="test:key",
        )

    assert result.applied is False
    assert result.reason == "user_not_found"


@pytest.mark.asyncio
async def test_claim_daily_first_time(engine, mock_session):
    maker, session = mock_session
    session.get.return_value = MagicMock(
        id="user-1",
        points=0,
        lifetime_points=0,
        daily_streak=0,
        last_daily_at=None,
        level=1,
    )
    session.execute.return_value.scalar_one_or_none.return_value = None

    with patch("bot.engines.points._get_session_maker", return_value=maker):
        result = await engine.claim_daily("user-1")

    assert result.applied is True
    assert result.streak == 1
    assert result.bonus == 2


@pytest.mark.asyncio
async def test_claim_daily_already_claimed(engine, mock_session):
    maker, session = mock_session
    session.get.return_value = MagicMock(
        id="user-1",
        points=100,
        lifetime_points=500,
        daily_streak=5,
        last_daily_at=datetime.now(timezone.utc),
        level=3,
    )

    with patch("bot.engines.points._get_session_maker", return_value=maker):
        result = await engine.claim_daily("user-1")

    assert result.applied is False
    assert result.reason == "already_claimed"


@pytest.mark.asyncio
async def test_claim_daily_user_not_found(engine, mock_session):
    maker, session = mock_session
    session.get.return_value = None

    with patch("bot.engines.points._get_session_maker", return_value=maker):
        result = await engine.claim_daily("nonexistent")

    assert result.applied is False
    assert result.reason == "user_not_found"


def test_level_formula():
    assert compute_level(0) == 1
    assert compute_level(100) == 2
    assert compute_level(400) == 3
    assert compute_level(900) == 4
