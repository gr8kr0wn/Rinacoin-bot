"""Tests for Scheduler — job registration, logging."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.scheduler import setup_scheduler, schedule, _log_and_run


def test_setup_registers_five_jobs():
    schedule.remove_all_jobs()
    setup_scheduler()
    jobs = schedule.get_jobs()
    job_ids = {j.id for j in jobs}
    assert "expire_stale_referrals" in job_ids
    assert "twitter_search" in job_ids
    assert "pet_decay" in job_ids
    assert "weekly_snapshot" in job_ids
    assert "loneliness_check" in job_ids
    schedule.remove_all_jobs()


@pytest.mark.asyncio
async def test_log_and_run_success():
    mock_fn = AsyncMock()
    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    mock_session.get = AsyncMock(return_value=MagicMock(finished_at=None))

    with patch("bot.scheduler.get_async_session", return_value=MagicMock(return_value=mock_session)):
        await _log_and_run("test_job", mock_fn)

    mock_fn.assert_awaited_once()


@pytest.mark.asyncio
async def test_log_and_run_error():
    async def failing_fn():
        raise ValueError("boom")

    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    mock_session.get = AsyncMock(return_value=MagicMock(finished_at=None, error=None))

    with patch("bot.scheduler.get_async_session", return_value=MagicMock(return_value=mock_session)):
        await _log_and_run("failing_job", failing_fn)

    # Should not raise, error is caught and logged
