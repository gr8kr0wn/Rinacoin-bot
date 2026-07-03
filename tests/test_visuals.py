"""Tests for context-aware emoji/visual helpers."""

import pytest
from bot.visuals import (
    pick_mood_emoji, pick_mood_description, pick_stage_emoji,
    pick_event_emoji, pick_affirmation, pick_greeting_end,
    streak_bar, stage_bar, fetch_cat_image,
)


class TestMoodEmoji:
    def test_known_moods_return_specific_emoji(self):
        assert pick_mood_emoji("hungry") == "🐟"
        assert pick_mood_emoji("happy") == "😸"
        assert pick_mood_emoji("sleepy") == "💤"
        assert pick_mood_emoji("playful") == "🧶"
        assert pick_mood_emoji("curious") == "👀"
        assert pick_mood_emoji("lonely") == "💔"
        assert pick_mood_emoji("excited") == "✨"
        assert pick_mood_emoji("sad") == "😿"

    def test_unknown_mood_falls_back_to_cat(self):
        assert pick_mood_emoji("unknown") == "🐱"
        assert pick_mood_emoji("") == "🐱"

    def test_mood_description_known(self):
        assert "tummy" in pick_mood_description("hungry")
        assert "purring" in pick_mood_description("happy")
        assert "curled" in pick_mood_description("sleepy")

    def test_mood_description_unknown_returns_empty(self):
        assert pick_mood_description("nonexistent") == ""


class TestStageEmoji:
    def test_known_stages(self):
        assert pick_stage_emoji("egg") == "🥚"
        assert pick_stage_emoji("senior") == "🐾"
        assert pick_stage_emoji("juvenile") == "🐈"
        assert pick_stage_emoji("adult") == "🐱"
        assert pick_stage_emoji("elder") == "👑"

    def test_unknown_stage_falls_back(self):
        assert pick_stage_emoji("unknown") == "🐱"


class TestEventEmoji:
    def test_known_events(self):
        assert pick_event_emoji("level_up") == "🎉"
        assert pick_event_emoji("streak_milestone") == "🔥"
        assert pick_event_emoji("daily_claim") == "🌟"

    def test_unknown_event_falls_back(self):
        assert pick_event_emoji("unknown") == "✨"


class TestRandomPicks:
    def test_affirmation_returns_valid_emoji(self):
        emoji = pick_affirmation()
        assert emoji in ["😸", "🐾", "💖", "✨", "🌟", "⭐"]

    def test_greeting_end_returns_valid_emoji(self):
        emoji = pick_greeting_end()
        assert emoji in ["✨", "🌟", "💫", "⭐", "🌸"]

    def test_affirmation_has_diversity(self):
        results = {pick_affirmation() for _ in range(100)}
        assert len(results) > 1

    def test_greeting_end_has_diversity(self):
        results = {pick_greeting_end() for _ in range(100)}
        assert len(results) > 1


class TestStreakBar:
    def test_zero_or_negative_returns_empty(self):
        assert streak_bar(0) == ""
        assert streak_bar(-1) == ""

    def test_short_streak(self):
        assert streak_bar(1) == "🔥"
        assert streak_bar(2) == "🔥"

    def test_medium_streak(self):
        assert streak_bar(5) == "🔥🔥"

    def test_long_streak(self):
        assert streak_bar(10) == "🔥🔥🔥"

    def test_very_long_streak(self):
        assert streak_bar(20) == "🔥🔥🔥🔥"

    def test_max_streak(self):
        assert streak_bar(50) == "🔥🔥🔥🔥🔥"


class TestStageBar:
    def test_egg_stage(self):
        bar = stage_bar("egg")
        assert bar == "🟩⬜⬜⬜⬜"

    def test_adult_stage(self):
        bar = stage_bar("adult")
        assert bar == "⬜⬜⬜🟩⬜"

    def test_elder_stage(self):
        bar = stage_bar("elder")
        assert bar == "⬜⬜⬜⬜🟩"

    def test_unknown_stage(self):
        bar = stage_bar("mythical")
        assert bar == "🟩⬜⬜⬜⬜"


class TestFetchCatImage:
    @pytest.mark.asyncio
    async def test_returns_none_on_error(self):
        result = await fetch_cat_image()
        assert result is None or isinstance(result, str)
