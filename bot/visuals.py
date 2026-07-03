"""Context-aware emoji, sticker, and image helpers — smart, not random."""

import random

# ── Stage emojis — literal growth indicators ────────────────────────────────

STAGE_EMOJIS = {
    "kitten": "🐱",
    "senior": "🐾",
    "juvenile": "🐈",
    "adult": "🐱",
    "elder": "👑",
}

# ── Mood emojis — precise match to Rina's current state ─────────────────────

MOOD_EMOJIS = {
    "hungry": "🐟",
    "happy": "😸",
    "sleepy": "💤",
    "playful": "🧶",
    "curious": "👀",
    "lonely": "💔",
    "excited": "✨",
    "sad": "😿",
}

# ── Mood descriptions ───────────────────────────────────────────────────────

MOOD_DESCRIPTIONS = {
    "hungry": "Rina's tummy is rumbling — feed the cat!",
    "happy": "Rina is purring softly.",
    "sleepy": "Rina is curled up, eyes half-closed...",
    "playful": "Rina is batting at everything that moves!",
    "curious": "Rina's ears perk up, head tilted.",
    "lonely": "Rina keeps looking at the door...",
    "excited": "Rina is zooming around like a maniac!",
    "sad": "Rina's tail is drooping...",
}

# ── Event-level emojis — triggered by specific game events ──────────────────

EVENT_EMOJIS = {
    "level_up": "🎉",
    "streak_milestone": "🔥",
    "referral": "🎁",
    "achievement": "🏆",
    "daily_claim": "🌟",
    "welcome": "👋",
    "leaderboard": "🏅",
    "profile": "📊",
    "referrals": "📨",
    "pet": "🐱",
}

# ── Emoji pools for variety in repeated contexts ────────────────────────────

_GREETING_END = ["✨", "🌟", "💫", "⭐", "🌸"]
_AFFIRMATION = ["😸", "🐾", "💖", "✨", "🌟", "⭐"]

# ── Public helpers ──────────────────────────────────────────────────────────

def pick_mood_emoji(mood: str) -> str:
    return MOOD_EMOJIS.get(mood, "🐱")


def pick_mood_description(mood: str) -> str:
    return MOOD_DESCRIPTIONS.get(mood, "")


def pick_stage_emoji(stage: str) -> str:
    return STAGE_EMOJIS.get(stage, "🐱")


def pick_event_emoji(event: str) -> str:
    return EVENT_EMOJIS.get(event, "✨")


def pick_affirmation() -> str:
    return random.choice(_AFFIRMATION)


def pick_greeting_end() -> str:
    return random.choice(_GREETING_END)


def streak_bar(streak: int) -> str:
    if streak <= 0:
        return ""
    if streak < 3:
        return "🔥"
    if streak < 7:
        return "🔥🔥"
    if streak < 14:
        return "🔥🔥🔥"
    if streak < 30:
        return "🔥🔥🔥🔥"
    return "🔥🔥🔥🔥🔥"


def stage_bar(stage: str) -> str:
    stages = ["kitten", "juvenile", "adult", "senior", "elder"]
    idx = stages.index(stage) if stage in stages else 0
    return "⬜" * idx + "🟩" + "⬜" * (len(stages) - idx - 1)


# ── Cat image fetcher ───────────────────────────────────────────────────────

async def fetch_cat_image() -> str | None:
    try:
        import aiohttp
        from bot.config import settings

        headers = {}
        if settings.cat_api_key:
            headers["x-api-key"] = settings.cat_api_key

        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://api.thecatapi.com/v1/images/search",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=3),
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                return data[0].get("url") if data else None
    except Exception:
        return None
