"""Tests for AiBrain — template fallback, Groq client, decision tree."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.ai.brain import AiBrain, _build_master_prompt, _build_user_message
from bot.ai.templates import pick_template


# ── Template fallback (pure, no mocks) ──────────────────────────────────────

def test_pick_template_returns_string():
    result = pick_template("daily_greeting", streak=5, points=12)
    assert isinstance(result, str)
    assert len(result) > 0


def test_pick_template_interpolates_all_vars():
    result = pick_template("daily_greeting", streak=3, points=10)
    assert "{streak}" not in result
    assert "{points}" not in result


def test_pick_template_invalid_type():
    assert pick_template("nonexistent") == "Meow."


def test_pick_template_all_types_produce_output():
    for pt in [
        "daily_greeting", "mood_change", "referral_reward",
        "achievement_unlock", "free_chat", "lonely_ping", "welcome",
    ]:
        text = pick_template(pt, streak=1, points=10, old_mood="sad",
                             new_mood="happy", stage="juvenile",
                             referrer_name="A", referred_name="B",
                             achievement_name="Test", message="Hi",
                             hours=6)
        assert isinstance(text, str) and len(text) > 0


# ── Master prompt builder (pure) ────────────────────────────────────────────

def test_build_master_prompt_contains_mood():
    prompt = _build_master_prompt(mood="excited", stage="adult", energy=80)
    assert "excited" in prompt
    assert "adult" in prompt
    assert "80/100" in prompt
    assert "bouncy and energetic" in prompt.lower()


def test_build_master_prompt_defaults():
    prompt = _build_master_prompt()
    assert "happy" in prompt
    assert "egg" in prompt
    assert "50/100" in prompt


def test_build_master_prompt_respects_max_length():
    prompt = _build_master_prompt(max_length=50)
    assert "50 characters" in prompt


# ── User message builder (pure) ─────────────────────────────────────────────

def test_build_user_message_free_chat():
    msg = _build_user_message("free_chat", message="hello world")
    assert "hello world" in msg


def test_build_user_message_daily_greeting():
    msg = _build_user_message("daily_greeting", streak=7, points=14)
    assert "7" in msg or "14" in msg


def test_build_user_message_welcome():
    msg = _build_user_message("welcome")
    assert "new user" in msg.lower() or "joined" in msg.lower()


# ── AiBrain decision tree (mocked) ─────────────────────────────────────────

@pytest.fixture
def brain():
    return AiBrain()


@pytest.mark.asyncio
async def test_no_api_key_uses_template(brain):
    with patch("bot.ai.brain.settings") as mock_settings:
        mock_settings.groq_api_key = ""
        with patch.object(brain, "_log_call", AsyncMock()):
            result = await brain.generate_reply("welcome", user_id="user-1")

    assert isinstance(result, str)
    assert len(result) > 0


def _make_groq_response(text: str):
    choice = MagicMock()
    choice.message.content = text
    resp = MagicMock()
    resp.choices = [choice]
    return resp


@pytest.mark.asyncio
async def test_groq_returns_text(brain):
    with patch("bot.ai.brain.settings") as mock_settings:
        mock_settings.groq_api_key = "fake-key"
        mock_settings.groq_model = "mixtral-8x7b-32768"
        with patch.object(brain, "_get_client") as mock_get:
            mock_client = MagicMock()
            mock_client.chat.completions.create = AsyncMock(
                return_value=_make_groq_response("Rina purrs happily!")
            )
            mock_get.return_value = mock_client
            with patch.object(brain, "_log_call", AsyncMock()):
                result = await brain.generate_reply(
                    "daily_greeting", user_id="user-1",
                    streak=5, points=10,
                )

    assert result == "Rina purrs happily!"


@pytest.mark.asyncio
async def test_groq_error_falls_back_to_template(brain):
    with patch("bot.ai.brain.settings") as mock_settings:
        mock_settings.groq_api_key = "fake-key"
        mock_settings.groq_model = "mixtral-8x7b-32768"
        with patch.object(brain, "_get_client") as mock_get:
            mock_client = MagicMock()
            mock_client.chat.completions.create = AsyncMock(
                side_effect=Exception("API error")
            )
            mock_get.return_value = mock_client
            with patch.object(brain, "_log_call", AsyncMock()):
                result = await brain.generate_reply("welcome", user_id="user-1")

    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.asyncio
async def test_groq_timeout_falls_back_to_template(brain):
    with patch("bot.ai.brain.settings") as mock_settings:
        mock_settings.groq_api_key = "fake-key"
        mock_settings.groq_model = "mixtral-8x7b-32768"
        with patch.object(brain, "_get_client") as mock_get:
            mock_client = MagicMock()
            mock_client.chat.completions.create = AsyncMock(
                side_effect=TimeoutError
            )
            mock_get.return_value = mock_client
            with patch.object(brain, "_log_call", AsyncMock()):
                result = await brain.generate_reply("lonely_ping", hours=6)

    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.asyncio
async def test_groq_empty_response_falls_back(brain):
    with patch("bot.ai.brain.settings") as mock_settings:
        mock_settings.groq_api_key = "fake-key"
        mock_settings.groq_model = "mixtral-8x7b-32768"
        with patch.object(brain, "_get_client") as mock_get:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.choices = []
            mock_client.chat.completions.create = AsyncMock(
                return_value=mock_response
            )
            mock_get.return_value = mock_client
            with patch.object(brain, "_log_call", AsyncMock()):
                result = await brain.generate_reply("welcome", user_id="user-1")

    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.asyncio
async def test_logging_is_called(brain):
    with patch("bot.ai.brain.settings") as mock_settings:
        mock_settings.groq_api_key = ""
        mock_log = AsyncMock()
        with patch.object(brain, "_log_call", mock_log):
            await brain.generate_reply("welcome", user_id="user-1")

    mock_log.assert_awaited_once()
    args, kwargs = mock_log.await_args
    assert kwargs["prompt_type"] == "welcome"
    assert kwargs["user_id"] == "user-1"
    assert isinstance(kwargs["output"], str)
    assert isinstance(kwargs["latency_ms"], int)
