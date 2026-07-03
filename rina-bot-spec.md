# Rina Bot — Specification & Progress

## Goal
Build Rina — a Telegram-native community companion bot with a virtual pet (cat), points economy, referral growth loop, and Groq-powered AI personality, deployed on Railway with Supabase Postgres.

## Stack
- Python 3.12, FastAPI, SQLAlchemy 2.0 (async), python-telegram-bot v22, APScheduler, loguru, pydantic-settings, groq
- Supabase Postgres (via asyncpg pooler for IPv4)
- Cat images from thecatapi.com

## Key Architecture Decisions
- Lazy DB engine init — `get_async_session()` returns session maker lazily, no engine at import time
- All three engines (points, referral, pet) use `_get_session_maker()` lazy function
- Pet engine import is lazy inside PointsEngine to avoid circular imports
- Rina is explicitly a cat
- AI Brain: Groq API with 2s timeout → template fallback on any error
- Rate limiter in-memory (sliding window deque per user)
- Sybil flags write to `admin_actions` for human review only

## Day 1 — Project Scaffold
- FastAPI entry point (`/health` GET, `/webhook` POST)
- `async_sessionmaker` lazy init
- All 9 SQLAlchemy ORM models
- Alembic migration `0f023d210eda_initial_schema`
- Engine stubs, 9 Telegram command stubs

## Day 2 — Points Engine
- `award_points` with idempotency (pg_insert + on_conflict_do_nothing)
- `claim_daily` with streak algorithm (resets on miss, bonus = min(streak×2, 50))
- `compute_level` (floor(sqrt(lifetime_points / 100)) + 1)
- `check_message_activity` anti-abuse (≥5 chars, no dup of last 3, 3s rate limit, 20/day cap)
- Referral hook after every award
- Telegram handlers: `/daily`, `/profile`, `/leaderboard`

## Day 2–3 — Referral Engine
- `register_referral`, `on_user_activity` (30 lifetime_points + 24h age → 50 pts reward)
- `expire_stale_referrals` (30 days)
- `ban_check` / `leave_check`
- `get_referral_stats` with shareable deep link
- `/start` processes `ref_{id}` param, `/myreferrals` dashboard

## Day 3 — Pet Engine
- Mood bucket resolution in priority order (§6.2)
- 5 trigger types (`points_awarded`, `pet_interaction`, `streak_broken`, `achievement_unlocked`, `decay`)
- Capped energy (0–100), mood_score (-100..100)
- 60s mood re-evaluation cooldown, 30min announcement cooldown
- Stage progression: egg→hatchling(1k)→juvenile(10k)→adult(50k)→elder(200k)
- `decay()` and `check_loneliness()` methods

## Day 4 — AI Brain
- `bot/ai/templates.py` — 5–7 cat-themed templates per prompt_type
- `bot/ai/brain.py` — master prompt builder, Groq client wrapper (2s timeout), `generate_reply()` decision tree
- Fallback: no API key → template, error/timeout → template, success → return Groq text
- Every call logged to `AiMessageLog` with latency and context

## Day 5 — Telegram Layer
- `/achievements` command
- Ambient message handler with `check_message_activity` + `free_chat` AI on @-mention
- Banned user middleware on all handlers
- AI Brain wired into `/start` (welcome), `/daily` (daily_greeting), `/pet` (free_chat)
- Inline keyboards: profile, leaderboard, referrals, pet, achievements, how-it-works
- Callback query handler

## Day 6 — Scheduler + Security
- 5 APScheduler cron jobs: expire_stale_referrals (00:00 UTC), twitter_search (10min), pet_decay (hourly), weekly_snapshot (weekly), loneliness_check (30min)
- All jobs logged to JobRun table
- `bot/security.py` — webhook verification, sliding-window rate limiter (10 cmd/min, 5 AI/min), sybil detection

## Day 7 — Visuals + Groq Switch + Local Testing
- **Emoji enhancements**: `bot/visuals.py` with contextual helpers (mood, stage, event emojis, streak bar, stage bar)
- **Cat images**: `fetch_cat_image()` from thecatapi.com (3s timeout, graceful None fallback)
- **AI switch**: Google Gemini → Groq (free API at api.groq.com)
- **Config**: `gemini_api_key` → `groq_api_key`, added `groq_model` (default: mixtral-8x7b-32768)
- **Dependencies**: `google-genai` → `groq==1.5.0`, added `aiohttp==3.14.1`
- **`.env` setup**: `TELEGRAM_BOT_TOKEN`, `GROQ_API_KEY`, `DATABASE_URL` (Supabase pooler)
- **DB migration**: Alembic applied to Supabase (IPv6 direct → IPv4 session pooler fix)
- **Polling fix**: Added `app.updater.start_polling()` in lifespan (PTB v22 doesn't start it automatically)
- **Callback fix**: Added missing handlers for referrals, pet, achievements nav buttons

## Test Count: 112 tests (all passing)

## Environment
- Telegram bot: @rinacoin_bot
- Groq model: mixtral-8x7b-32768
- Database: Supabase Postgres (session pooler)
- Local dev: http://localhost:3000

## To Start Bot Locally
```bash
cd C:\Users\HP\Desktop\Rina-coin
python -m uvicorn bot.main:app --port 3000
```
