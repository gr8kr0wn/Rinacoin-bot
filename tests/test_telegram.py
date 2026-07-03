"""Tests for Telegram adapter handlers with mocked Update/Context."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import Update, Message, User as TgUser, Chat

from bot.adapters.telegram import (
    start, daily, profile, leaderboard, pet,
    myreferrals, achievements, help_command,
    handle_message, handle_callback,
)


def _make_update(text: str = "", chat_id: int = -100, user_id: int = 1, username: str = "testuser", message_id: int = 1) -> MagicMock:
    user = MagicMock(spec=TgUser)
    user.id = user_id
    user.username = username
    user.is_bot = False

    chat = MagicMock(spec=Chat)
    chat.id = chat_id

    message = MagicMock(spec=Message)
    message.text = text
    message.message_id = message_id
    message.reply_text = AsyncMock()
    message.entities = []

    update = MagicMock(spec=Update)
    update.effective_user = user
    update.effective_chat = chat
    update.message = message
    update.callback_query = None

    return update


def _make_context() -> MagicMock:
    ctx = MagicMock()
    ctx.args = []
    ctx.bot = MagicMock()
    return ctx


@pytest.mark.asyncio
async def test_start_creates_user_and_sends_welcome():
    update = _make_update()
    context = _make_context()

    with patch("bot.adapters.telegram._get_or_create_user", AsyncMock(return_value=(MagicMock(id="u1", is_banned=False), True))):
        with patch("bot.adapters.telegram.ai_brain") as mock_brain:
            mock_brain.generate_reply = AsyncMock(return_value="Meow! Welcome!")
            with patch("bot.adapters.telegram._is_banned", AsyncMock(return_value=False)):
                await start(update, context)

    update.message.reply_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_achievements_shows_list():
    update = _make_update()
    context = _make_context()

    mock_ach1 = MagicMock(id="a1", code="first", name="First Steps", description="Send a message", icon="⭐", points_reward=10)
    mock_ach2 = MagicMock(id="a2", code="streak3", name="Streak 3", description="3-day streak", icon="🔥", points_reward=20)

    with patch("bot.adapters.telegram._get_or_create_user", AsyncMock(return_value=(MagicMock(id="u1", is_banned=False), False))):
        with patch("bot.adapters.telegram._is_banned", AsyncMock(return_value=False)):
            with patch("bot.adapters.telegram.get_async_session") as mock_session_maker:
                mock_session = MagicMock()
                mock_session.__aenter__ = AsyncMock(return_value=mock_session)
                mock_session.__aexit__ = AsyncMock(return_value=None)

                exec_result_all = MagicMock()
                exec_result_all.scalars.return_value.all.return_value = [mock_ach1, mock_ach2]

                exec_result_unlocked = MagicMock()
                exec_result_unlocked.scalars.return_value.all.return_value = ["a1"]

                mock_session.execute = AsyncMock()
                mock_session.execute.side_effect = [exec_result_all, exec_result_unlocked]

                mock_session_maker.return_value = MagicMock(return_value=mock_session)

                await achievements(update, context)

    update.message.reply_text.assert_awaited_once()
    text = update.message.reply_text.await_args[0][0]
    assert "✅" in text
    assert "🔒" in text
    assert "First Steps" in text
    assert "Streak 3" in text


@pytest.mark.asyncio
async def test_banned_user_gets_rejected():
    update = _make_update()
    context = _make_context()

    with patch("bot.adapters.telegram._is_banned", AsyncMock(return_value=True)):
        await help_command(update, context)

    update.message.reply_text.assert_awaited_once()
    assert "doesn't recognize" in update.message.reply_text.await_args[0][0]


@pytest.mark.asyncio
async def test_handle_message_calls_points_and_pet():
    update = _make_update(text="hello world")
    context = _make_context()

    with patch("bot.adapters.telegram._get_or_create_user", AsyncMock(return_value=(MagicMock(id="u1"), False))):
        with patch("bot.adapters.telegram._is_banned", AsyncMock(return_value=False)):
            with patch("bot.adapters.telegram._is_mentioned", AsyncMock(return_value=False)):
                with patch("bot.adapters.telegram.points_engine") as mock_pts:
                    mock_pts.check_message_activity = AsyncMock()
                    await handle_message(update, context)

    mock_pts.check_message_activity.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_message_mention_triggers_ai():
    update = _make_update(text=f"@RinaBot hello!")
    context = _make_context()

    with patch("bot.adapters.telegram._get_or_create_user", AsyncMock(return_value=(MagicMock(id="u1"), False))):
        with patch("bot.adapters.telegram._is_banned", AsyncMock(return_value=False)):
            with patch("bot.adapters.telegram._is_mentioned", AsyncMock(return_value=True)):
                with patch("bot.adapters.telegram.points_engine") as mock_pts:
                    mock_pts.check_message_activity = AsyncMock()
                    with patch("bot.adapters.telegram.ai_brain") as mock_brain:
                        mock_brain.generate_reply = AsyncMock(return_value="Rina meows back!")
                        await handle_message(update, context)

    update.message.reply_text.assert_awaited_once()
    assert "Rina meows back!" in update.message.reply_text.await_args[0][0]


@pytest.mark.asyncio
async def test_profile_shows_stats():
    update = _make_update()
    context = _make_context()

    mock_user = MagicMock(
        id="u1", level=5, points=250, daily_streak=7,
        joined_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        is_banned=False,
    )

    with patch("bot.adapters.telegram._get_or_create_user", AsyncMock(return_value=(mock_user, False))):
        with patch("bot.adapters.telegram._is_banned", AsyncMock(return_value=False)):
            await profile(update, context)

    update.message.reply_text.assert_awaited_once()
    text = update.message.reply_text.await_args[0][0]
    assert "Level: 5" in text
    assert "250" in text
    assert "7" in text


@pytest.mark.asyncio
async def test_pet_interaction():
    update = _make_update(chat_id=-42)
    context = _make_context()

    with patch("bot.adapters.telegram._get_or_create_user", AsyncMock(return_value=(MagicMock(id="u1"), False))):
        with patch("bot.adapters.telegram._is_banned", AsyncMock(return_value=False)):
            with patch("bot.adapters.telegram.fetch_cat_image", AsyncMock(return_value=None)):
                with patch("bot.adapters.telegram.pet_engine") as mock_pet:
                    mock_pet.on_event = AsyncMock()
                    with patch("bot.adapters.telegram.ai_brain") as mock_brain:
                        mock_brain.generate_reply = AsyncMock(return_value="Rina purrs!")
                        await pet(update, context)

    from bot.engines.pet import PetTriggerEvent
    mock_pet.on_event.assert_awaited_once_with(-42, PetTriggerEvent(type="pet_interaction"))
    update.message.reply_text.assert_awaited_once()


from datetime import datetime, timezone


@pytest.mark.asyncio
async def test_callback_leaderboard():
    query = MagicMock()
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    query.data = "nav:leaderboard"
    query.from_user = MagicMock(id=1, username="test")

    update = MagicMock(spec=Update)
    update.callback_query = query
    update.effective_user = query.from_user
    update.effective_chat = MagicMock(id=-100)

    with patch("bot.adapters.telegram.points_engine") as mock_pts:
        entry = MagicMock(user_id="u1", username="alice", points=100, level=3, rank=1)
        mock_pts.get_leaderboard = AsyncMock(return_value=[entry])
        await handle_callback(update, MagicMock())

    query.answer.assert_awaited_once()
    query.edit_message_text.assert_awaited_once()
