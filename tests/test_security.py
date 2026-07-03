"""Tests for Security — webhook verification, rate limiter, sybil detection."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from datetime import datetime, timezone

from bot.security import (
    verify_webhook_secret,
    RateLimiter,
    check_command_rate,
    check_ai_rate,
    flag_suspicious_referral,
)


# ── Webhook verification ────────────────────────────────────────────────────

def test_verify_webhook_matches():
    with patch("bot.security.settings") as mock:
        mock.telegram_webhook_secret = "secret123"
        assert verify_webhook_secret("secret123") is True


def test_verify_webhook_mismatch():
    with patch("bot.security.settings") as mock:
        mock.telegram_webhook_secret = "secret123"
        assert verify_webhook_secret("wrong") is False


def test_verify_webhook_no_secret_configured():
    with patch("bot.security.settings") as mock:
        mock.telegram_webhook_secret = ""
        assert verify_webhook_secret(None) is True
        assert verify_webhook_secret("anything") is True


# ── Rate limiter ────────────────────────────────────────────────────────────

def test_rate_limiter_allows_within_limit():
    limiter = RateLimiter(max_requests=3, window_seconds=60)
    assert limiter.check(1) is True
    assert limiter.check(1) is True
    assert limiter.check(1) is True


def test_rate_limiter_blocks_excess():
    limiter = RateLimiter(max_requests=3, window_seconds=60)
    assert limiter.check(1) is True
    assert limiter.check(1) is True
    assert limiter.check(1) is True
    assert limiter.check(1) is False


def test_rate_limiter_reset():
    limiter = RateLimiter(max_requests=2, window_seconds=60)
    assert limiter.check(1) is True
    assert limiter.check(1) is True
    assert limiter.check(1) is False
    limiter.reset(1)
    assert limiter.check(1) is True


def test_rate_limiter_separate_users():
    limiter = RateLimiter(max_requests=2, window_seconds=60)
    assert limiter.check(1) is True
    assert limiter.check(1) is True
    assert limiter.check(2) is True  # different user not blocked
    assert limiter.check(1) is False


def test_command_limiter_exists():
    assert check_command_rate(1) is True or check_command_rate(1) is False


def test_ai_limiter_exists():
    assert check_ai_rate(1) is True or check_ai_rate(1) is False


# ── Sybil detection ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_flag_suspicious_same_minute_signup():
    mock_referred = MagicMock(
        id="u2", joined_at=datetime(2026, 7, 2, 12, 0, 30, tzinfo=timezone.utc),
        lifetime_points=0, referred_by="u1",
    )
    mock_referrer = MagicMock(
        id="u1", joined_at=datetime(2026, 7, 2, 12, 0, 0, tzinfo=timezone.utc),
    )

    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    mock_session.get = AsyncMock(side_effect=[mock_referred, mock_referrer])
    mock_session.execute = AsyncMock(return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))))

    with patch("bot.security.get_async_session", return_value=MagicMock(return_value=mock_session)):
        await flag_suspicious_referral("u1", "u2")

    mock_session.add.assert_called()


@pytest.mark.asyncio
async def test_flag_suspicious_no_flags_for_normal():
    mock_referred = MagicMock(
        id="u2", joined_at=datetime(2026, 7, 2, 12, 0, 0, tzinfo=timezone.utc),
        lifetime_points=10, referred_by="u1",
    )
    mock_referrer = MagicMock(
        id="u1", joined_at=datetime(2026, 7, 1, 0, 0, 0, tzinfo=timezone.utc),
    )

    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    mock_session.get = AsyncMock(side_effect=[mock_referred, mock_referrer])
    mock_session.execute = AsyncMock(return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))))

    with patch("bot.security.get_async_session", return_value=MagicMock(return_value=mock_session)):
        await flag_suspicious_referral("u1", "u2")

    mock_session.add.assert_not_called()
