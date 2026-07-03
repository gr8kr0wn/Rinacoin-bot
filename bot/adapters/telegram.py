from uuid import uuid4
from datetime import datetime, timezone

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters

from sqlalchemy import select
from bot.config import settings
from bot.db.database import get_async_session
from bot.db.models import User, Achievement, UserAchievement
from bot.engines.points import points_engine
from bot.engines.referral import referral_engine
from bot.engines.pet import pet_engine, PetTriggerEvent
from bot.ai.brain import ai_brain
from bot.visuals import (
    pick_mood_emoji, pick_mood_description, pick_stage_emoji, pick_event_emoji,
    pick_affirmation, pick_greeting_end, streak_bar, stage_bar, fetch_cat_image,
)


BOT_USERNAME = "RinaBot"


# ── Helpers ─────────────────────────────────────────────────────────────────

async def _get_or_create_user(telegram_id: int, username: str | None = None) -> tuple[User | None, bool]:
    async with get_async_session()() as session:
        async with session.begin():
            result = await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            user = result.scalar_one_or_none()
            if user:
                user.last_seen_at = datetime.now(timezone.utc)
                if username:
                    user.username = username
                return user, False

            user = User(
                id=uuid4(),
                telegram_id=telegram_id,
                username=username,
            )
            session.add(user)
            return user, True


async def _is_mentioned(message) -> bool:
    if not message.entities:
        return False
    for entity in message.entities:
        if entity.type == "mention" and message.text[entity.offset:entity.offset + entity.length].lstrip("@").lower() == BOT_USERNAME.lower():
            return True
        if entity.type == "text_mention" and getattr(entity.user, "is_bot", False):
            return True
    return False


async def _is_banned(telegram_id: int) -> bool:
    async with get_async_session()() as session:
        result = await session.execute(
            select(User.is_banned).where(User.telegram_id == telegram_id)
        )
        banned = result.scalar_one_or_none()
        return banned is True


async def _check_banned(update: Update) -> bool:
    if not update.effective_user:
        return True
    if await _is_banned(update.effective_user.id):
        if update.message:
            await update.message.reply_text("Rina doesn't recognize you.")
        return True
    return False


def _profile_keyboard(user_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🏆 Leaderboard", callback_data="nav:leaderboard"),
            InlineKeyboardButton("📨 Referrals", callback_data=f"nav:referrals:{user_id}"),
        ],
        [
            InlineKeyboardButton("🐾 Pet", callback_data=f"nav:pet:{user_id}"),
            InlineKeyboardButton("🏅 Achievements", callback_data=f"nav:achievements:{user_id}"),
        ],
    ])


def _how_it_works_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 View Profile", callback_data="nav:profile")],
    ])


# ── Handlers ────────────────────────────────────────────────────────────────

async def start(update: Update, context):
    if not update.effective_user:
        return
    if await _check_banned(update):
        return
    user, is_new = await _get_or_create_user(
        update.effective_user.id, update.effective_user.username,
    )
    if not user:
        await update.message.reply_text("Something went wrong.")
        return

    ref_code = None
    if context.args:
        ref_code = context.args[0]

    if is_new and ref_code and ref_code.startswith("ref_"):
        referrer_id = ref_code[4:]
        if referrer_id != str(user.id):
            err = await referral_engine.register_referral(referrer_id, str(user.id))
            if err is None:
                await update.message.reply_text("You were referred by a friend! 🎁")

    welcome = await ai_brain.generate_reply("welcome", user_id=str(user.id))
    end = pick_greeting_end()
    await update.message.reply_text(
        f"{welcome} {end}\n\nUse /daily to claim your first points!",
        reply_markup=_how_it_works_keyboard(),
    )


async def daily(update: Update, _context):
    if not update.effective_user or not update.effective_chat:
        return
    if await _check_banned(update):
        return
    user, _ = await _get_or_create_user(update.effective_user.id, update.effective_user.username)
    if not user:
        return

    result = await points_engine.claim_daily(str(user.id), community_id=update.effective_chat.id)
    if not result.applied:
        if result.reason == "already_claimed":
            await update.message.reply_text("You already claimed your daily points today! Come back tomorrow 🌙")
        elif result.reason == "duplicate":
            await update.message.reply_text("Already processed — no double-dipping 😉")
        else:
            await update.message.reply_text(f"Couldn't claim: {result.reason}")
        return

    total = 10 + (result.bonus or 0)
    sbar = streak_bar(result.streak or 1)
    emoji = pick_event_emoji("daily_claim")

    ai_reply = await ai_brain.generate_reply(
        "daily_greeting", user_id=str(user.id),
        streak=result.streak or 1, points=total,
    )

    msg = f"{emoji} {ai_reply}\n\n{sbar} Streak: {result.streak} day{'s' if (result.streak or 0) > 1 else ''}"
    if result.bonus:
        msg += f"\nBonus: +{result.bonus}"
    if result.new_level:
        lvl_emoji = pick_event_emoji("level_up")
        msg += f"\n{lvl_emoji} Level up! You're now level {result.new_level}!"
    await update.message.reply_text(msg)


async def profile(update: Update, _context):
    if not update.effective_user:
        return
    if await _check_banned(update):
        return
    user, _ = await _get_or_create_user(update.effective_user.id, update.effective_user.username)
    if not user:
        return

    emoji = pick_event_emoji("profile")
    aff = pick_affirmation()

    await update.message.reply_text(
        f"{emoji} Profile {aff}\n\n"
        f"Level: {user.level}\n"
        f"Points: {user.points}\n"
        f"{streak_bar(user.daily_streak)} Streak: {user.daily_streak} days\n"
        f"Joined: {user.joined_at.strftime('%Y-%m-%d') if user.joined_at else 'N/A'}",
        reply_markup=_profile_keyboard(str(user.id)),
    )


async def leaderboard(update: Update, _context):
    if not update.effective_user:
        return
    if await _check_banned(update):
        return
    entries = await points_engine.get_leaderboard(10)
    if not entries:
        await update.message.reply_text("No one on the leaderboard yet. Be the first!")
        return

    medal = {1: "🥇", 2: "🥈", 3: "🥉"}
    emoji = pick_event_emoji("leaderboard")
    lines = [f"{emoji} Leaderboard\n"]
    for e in entries:
        prefix = medal.get(e.rank, f"{e.rank}.")
        name = e.username or f"User {e.user_id[:8]}"
        lines.append(f"{prefix} {name} — {e.points} pts (lvl {e.level})")
    await update.message.reply_text("\n".join(lines))


async def pet(update: Update, _context):
    if not update.effective_user or not update.effective_chat:
        return
    if await _check_banned(update):
        return
    user, _ = await _get_or_create_user(update.effective_user.id, update.effective_user.username)
    if not user:
        return

    result = await pet_engine.on_event(
        update.effective_chat.id,
        PetTriggerEvent(type="pet_interaction"),
    )

    mood_emoji = pick_mood_emoji(result.mood)
    stage_emoji = pick_stage_emoji(result.stage)
    desc = pick_mood_description(result.mood)

    ai_reply = await ai_brain.generate_reply(
        "free_chat", user_id=str(user.id),
        message="*pets Rina*",
        mood=result.mood, stage=result.stage, energy=result.energy,
    )

    msg = f"{ai_reply} {mood_emoji}\n{desc}\nMood: {result.mood} {stage_bar(result.stage)} Stage: {result.stage} | Energy: {result.energy}/100"
    if result.mood_changed:
        msg += "\n✨ Rina's mood shifted!"
    if result.stage_changed:
        msg += f"\n🌟 Rina grew to a new stage! {stage_emoji}"

    cat_url = await fetch_cat_image()
    if cat_url:
        await update.message.reply_photo(photo=cat_url, caption=msg)
    else:
        await update.message.reply_text(msg)


async def myreferrals(update: Update, _context):
    if not update.effective_user:
        return
    if await _check_banned(update):
        return
    user, _ = await _get_or_create_user(update.effective_user.id, update.effective_user.username)
    if not user:
        return

    stats = await referral_engine.get_referral_stats(str(user.id))
    emoji = pick_event_emoji("referrals")
    await update.message.reply_text(
        f"{emoji} Referrals\n\n"
        f"Total invited: {stats.total_invited}\n"
        f"Pending: {stats.pending}\n"
        f"Qualified: {stats.qualified}\n"
        f"Points earned: {stats.total_points_earned}\n\n"
        f"Share your link:\n{stats.shareable_link}"
    )


async def achievements(update: Update, _context):
    if not update.effective_user:
        return
    if await _check_banned(update):
        return
    user, _ = await _get_or_create_user(update.effective_user.id, update.effective_user.username)
    if not user:
        return

    async with get_async_session()() as session:
        all_achievements = await session.execute(
            select(Achievement).order_by(Achievement.code)
        )
        all_achs = all_achievements.scalars().all()

        unlocked = await session.execute(
            select(UserAchievement.achievement_id).where(
                UserAchievement.user_id == user.id
            )
        )
        unlocked_ids = set(unlocked.scalars().all())

    if not all_achs:
        await update.message.reply_text("No achievements exist yet. Rina will add some soon!")
        return

    emoji = pick_event_emoji("achievement")
    lines = [f"{emoji} Achievements\n"]
    for a in all_achs:
        unlocked_str = "✅" if a.id in unlocked_ids else "🔒"
        icon = a.icon or ""
        lines.append(f"{unlocked_str} {icon} {a.name} — {a.description}")
    await update.message.reply_text("\n".join(lines))


async def help_command(update: Update, _context):
    if await _check_banned(update):
        return
    await update.message.reply_text(
        "Available commands:\n"
        "/start — Onboarding\n"
        "/daily — Claim daily points\n"
        "/profile — View your stats\n"
        "/leaderboard — Top 10 by points\n"
        "/pet — Pet Rina 🐱\n"
        "/myreferrals — Referral dashboard\n"
        "/achievements — View achievements\n"
        "/help — This message"
    )


# ── Ambient message handler ─────────────────────────────────────────────────

async def handle_message(update: Update, _context):
    if not update.effective_user or not update.effective_chat or not update.message:
        return
    if await _check_banned(update):
        return

    user, _ = await _get_or_create_user(update.effective_user.id, update.effective_user.username)
    if not user:
        return

    text = update.message.text or ""
    community_id = update.effective_chat.id
    msg_id = update.message.message_id

    await points_engine.check_message_activity(
        str(user.id), text, msg_id, community_id=community_id,
    )

    if await _is_mentioned(update.message):
        mention_text = text.replace(f"@{BOT_USERNAME}", "").replace(f"@{BOT_USERNAME.lower()}", "").strip()
        if not mention_text:
            mention_text = "*Rina is addressed*"
        reply = await ai_brain.generate_reply(
            "free_chat", user_id=str(user.id),
            message=mention_text or "...",
        )
        await update.message.reply_text(reply)


# ── Callback query handler ──────────────────────────────────────────────────

async def handle_callback(update: Update, _context):
    query = update.callback_query
    await query.answer()
    if not query.data:
        return

    parts = query.data.split(":", 2)
    action = parts[0] if len(parts) > 0 else ""

    if action != "nav":
        return

    nav_type = parts[1] if len(parts) > 1 else ""
    nav_user_id = parts[2] if len(parts) > 2 else None

    if nav_type == "profile":
        user, _ = await _get_or_create_user(query.from_user.id, query.from_user.username)
        if not user:
            return
        await query.edit_message_text(
            f"{pick_event_emoji('profile')} Profile {pick_affirmation()}\n\n"
            f"Level: {user.level}\n"
            f"Points: {user.points}\n"
            f"{streak_bar(user.daily_streak)} Streak: {user.daily_streak} days\n"
            f"Joined: {user.joined_at.strftime('%Y-%m-%d') if user.joined_at else 'N/A'}",
            reply_markup=_profile_keyboard(str(user.id)),
        )

    elif nav_type == "leaderboard":
        entries = await points_engine.get_leaderboard(10)
        if not entries:
            await query.edit_message_text("No one on the leaderboard yet.")
            return
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}
        lines = [f"{pick_event_emoji('leaderboard')} Leaderboard\n"]
        for e in entries:
            prefix = medal.get(e.rank, f"{e.rank}.")
            name = e.username or f"User {e.user_id[:8]}"
            lines.append(f"{prefix} {name} — {e.points} pts (lvl {e.level})")
        await query.edit_message_text("\n".join(lines))

    elif nav_type == "referrals" and nav_user_id:
        user, _ = await _get_or_create_user(query.from_user.id, query.from_user.username)
        if not user:
            return
        stats = await referral_engine.get_referral_stats(nav_user_id)
        emoji = pick_event_emoji("referrals")
        await query.edit_message_text(
            f"{emoji} Referrals\n\n"
            f"Total invited: {stats.total_invited}\n"
            f"Pending: {stats.pending}\n"
            f"Qualified: {stats.qualified}\n"
            f"Points earned: {stats.total_points_earned}\n\n"
            f"Share your link:\n{stats.shareable_link}",
            reply_markup=_profile_keyboard(nav_user_id),
        )

    elif nav_type == "pet" and nav_user_id:
        result = await pet_engine.on_event(
            query.message.chat_id if query.message else 0,
            PetTriggerEvent(type="pet_interaction"),
        )
        mood_emoji = pick_mood_emoji(result.mood)
        stage_emoji = pick_stage_emoji(result.stage)
        desc = pick_mood_description(result.mood)
        msg = f"{pick_event_emoji('pet')} Pet Rina\n{mood_emoji} {desc}\nMood: {result.mood} {stage_bar(result.stage)} Stage: {result.stage} | Energy: {result.energy}/100"
        if result.mood_changed:
            msg += "\n✨ Rina's mood shifted!"
        if result.stage_changed:
            msg += f"\n🌟 Rina grew to a new stage! {stage_emoji}"
        await query.edit_message_text(msg, reply_markup=_profile_keyboard(nav_user_id))

    elif nav_type == "achievements" and nav_user_id:
        async with get_async_session()() as session:
            all_achievements = await session.execute(
                select(Achievement).order_by(Achievement.code)
            )
            all_achs = all_achievements.scalars().all()
            unlocked = await session.execute(
                select(UserAchievement.achievement_id).where(
                    UserAchievement.user_id == nav_user_id
                )
            )
            unlocked_ids = set(unlocked.scalars().all())

        if not all_achs:
            await query.edit_message_text("No achievements exist yet. Rina will add some soon!")
            return

        emoji = pick_event_emoji("achievement")
        lines = [f"{emoji} Achievements\n"]
        for a in all_achs:
            unlocked_str = "✅" if a.id in unlocked_ids else "🔒"
            icon = a.icon or ""
            lines.append(f"{unlocked_str} {icon} {a.name} — {a.description}")
        await query.edit_message_text("\n".join(lines), reply_markup=_profile_keyboard(nav_user_id))


# ── Application factory ─────────────────────────────────────────────────────

def create_application() -> Application:
    app = Application.builder().token(settings.telegram_bot_token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("daily", daily))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("leaderboard", leaderboard))
    app.add_handler(CommandHandler("pet", pet))
    app.add_handler(CommandHandler("myreferrals", myreferrals))
    app.add_handler(CommandHandler("achievements", achievements))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(handle_callback))

    return app
