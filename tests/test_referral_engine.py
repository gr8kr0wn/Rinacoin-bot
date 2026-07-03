"""Tests for Referral Engine covering all §5.2 scenarios."""

from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from bot.engines.referral import ReferralEngine


@pytest.fixture
def engine():
    return ReferralEngine()


def _make_mock_session():
    session = AsyncMock(spec=AsyncSession)

    begin_cm = MagicMock()
    begin_cm.__aenter__ = AsyncMock(return_value=session)
    begin_cm.__aexit__ = AsyncMock(return_value=None)
    session.begin.return_value = begin_cm

    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=session)
    session_cm.__aexit__ = AsyncMock(return_value=None)

    maker = MagicMock(return_value=session_cm)

    result_mock = MagicMock()
    session.execute.return_value = result_mock

    scalars_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock

    return maker, session, result_mock, scalars_mock


@pytest.mark.asyncio
async def test_register_referral_success():
    engine = ReferralEngine()
    maker, session, result_mock, _ = _make_mock_session()
    session.get.side_effect = [
        MagicMock(id="referrer-1", points=100),
        MagicMock(id="new-1", points=0, referred_by=None),
    ]
    result_mock.scalar_one_or_none.return_value = None

    with patch("bot.engines.referral._get_session_maker", return_value=maker):
        err = await engine.register_referral("referrer-1", "new-1")

    assert err is None


@pytest.mark.asyncio
async def test_self_referral_rejected():
    engine = ReferralEngine()
    maker, session, _, _ = _make_mock_session()

    with patch("bot.engines.referral._get_session_maker", return_value=maker):
        err = await engine.register_referral("same-user", "same-user")

    assert err == "self_referral"


@pytest.mark.asyncio
async def test_duplicate_referral_ignored():
    engine = ReferralEngine()
    maker, session, result_mock, _ = _make_mock_session()
    session.get.side_effect = [
        MagicMock(id="referrer-1", points=100),
        MagicMock(id="new-1", points=0, referred_by="existing-ref"),
    ]

    with patch("bot.engines.referral._get_session_maker", return_value=maker):
        err = await engine.register_referral("referrer-1", "new-1")

    assert err == "already_referred"


@pytest.mark.asyncio
async def test_register_referrer_not_found():
    engine = ReferralEngine()
    maker, session, result_mock, _ = _make_mock_session()
    session.get.side_effect = [None]

    with patch("bot.engines.referral._get_session_maker", return_value=maker):
        err = await engine.register_referral("nonexistent", "new-1")

    assert err == "referrer_not_found"


@pytest.mark.asyncio
async def test_qualification_triggers_reward():
    engine = ReferralEngine()
    maker, session, result_mock, scalars_mock = _make_mock_session()

    pending_ref = MagicMock()
    pending_ref.id = "ref-1"
    pending_ref.referrer_id = "referrer-1"
    pending_ref.status = "pending"

    result_mock.scalar_one_or_none.return_value = pending_ref

    session.get.return_value = MagicMock(
        id="new-1",
        lifetime_points=50,
        joined_at=datetime.now(timezone.utc) - timedelta(hours=48),
    )

    with patch("bot.engines.referral._get_session_maker", return_value=maker):
        with patch("bot.engines.referral.REFERRAL_REWARD", 50):
            with patch("bot.engines.points.points_engine") as mock_pts:
                mock_pts.award_points = AsyncMock(return_value=MagicMock(applied=True))
                await engine.on_user_activity("new-1")

    assert pending_ref.status == "rewarded"


@pytest.mark.asyncio
async def test_qualification_not_enough_points():
    engine = ReferralEngine()
    maker, session, result_mock, scalars_mock = _make_mock_session()

    pending_ref = MagicMock()
    pending_ref.status = "pending"

    result_mock.scalar_one_or_none.return_value = pending_ref
    session.get.return_value = MagicMock(
        id="new-1",
        lifetime_points=10,
        joined_at=datetime.now(timezone.utc) - timedelta(hours=48),
    )

    with patch("bot.engines.referral._get_session_maker", return_value=maker):
        await engine.on_user_activity("new-1")

    assert pending_ref.status == "pending"


@pytest.mark.asyncio
async def test_qualification_not_enough_time():
    engine = ReferralEngine()
    maker, session, result_mock, scalars_mock = _make_mock_session()

    pending_ref = MagicMock()
    pending_ref.status = "pending"

    result_mock.scalar_one_or_none.return_value = pending_ref
    session.get.return_value = MagicMock(
        id="new-1",
        lifetime_points=50,
        joined_at=datetime.now(timezone.utc) - timedelta(hours=2),
    )

    with patch("bot.engines.referral._get_session_maker", return_value=maker):
        await engine.on_user_activity("new-1")

    assert pending_ref.status == "pending"


@pytest.mark.asyncio
async def test_ban_marks_pending_as_rejected():
    engine = ReferralEngine()
    maker, session, result_mock, scalars_mock = _make_mock_session()

    ref_mock = MagicMock()
    ref_mock.status = "pending"
    ref_mock.rejection_reason = None

    scalars_mock.all.return_value = [ref_mock]

    with patch("bot.engines.referral._get_session_maker", return_value=maker):
        await engine.ban_check("new-1")

    assert ref_mock.status == "rejected"
    assert ref_mock.rejection_reason == "banned"


@pytest.mark.asyncio
async def test_leave_marks_pending_as_rejected():
    engine = ReferralEngine()
    maker, session, result_mock, scalars_mock = _make_mock_session()

    ref_mock = MagicMock()
    ref_mock.status = "pending"
    ref_mock.rejection_reason = None

    scalars_mock.all.return_value = [ref_mock]

    with patch("bot.engines.referral._get_session_maker", return_value=maker):
        await engine.leave_check("new-1")

    assert ref_mock.status == "rejected"
    assert ref_mock.rejection_reason == "left_before_qualifying"


@pytest.mark.asyncio
async def test_expire_stale_referrals():
    engine = ReferralEngine()
    maker, session, result_mock, scalars_mock = _make_mock_session()

    stale = MagicMock()
    stale.status = "pending"
    stale.rejection_reason = None

    scalars_mock.all.return_value = [stale]

    with patch("bot.engines.referral._get_session_maker", return_value=maker):
        count = await engine.expire_stale_referrals()

    assert count == 1
    assert stale.status == "rejected"
    assert stale.rejection_reason == "inactive_30d"


@pytest.mark.asyncio
async def test_get_referral_stats():
    engine = ReferralEngine()
    maker, session, result_mock, scalars_mock = _make_mock_session()

    ref_pending = MagicMock(status="pending")
    ref_qualified = MagicMock(status="qualified")
    ref_rewarded = MagicMock(status="rewarded")

    scalars_mock.all.side_effect = [
        [ref_pending, ref_qualified, ref_rewarded],
        [ref_rewarded],
    ]

    with patch("bot.engines.referral._get_session_maker", return_value=maker):
        stats = await engine.get_referral_stats("referrer-1")

    assert stats.total_invited == 3
    assert stats.pending == 1
    assert stats.qualified == 2
    assert stats.total_points_earned == 50
    assert "ref_referrer-1" in stats.shareable_link
