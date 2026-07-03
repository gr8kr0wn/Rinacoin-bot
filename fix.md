# Rina Bot — Fix List
### Compiled from full codebase review against `rina-bot-spec.md`
### Everything found, nothing held back.

Legend: 🔴 Bug (breaks correct behavior) · 🟡 Gap (spec/UX feature missing or dead code) · 🟢 Cosmetic/naming

---

## 🔴 Bugs — things that are actively wrong

### 1. Message-activity daily cap is effectively 1, not 20
**File:** `bot/engines/points.py`, line 237
```python
if daily_count.scalar() or 0 >= DAILY_MESSAGE_CAP:
```
Operator precedence bug — parses as `daily_count.scalar() or (0 >= DAILY_MESSAGE_CAP)`. `0 >= 20` is always `False`, so the check collapses to just `bool(daily_count.scalar())`. The moment a user has **one** message-activity point today, every later message that day is rejected as "cap reached."
**Fix:**
```python
if (daily_count.scalar() or 0) >= DAILY_MESSAGE_CAP:
```

### 2. `/daily` can double-credit points under concurrent requests
**File:** `bot/engines/points.py`, `claim_daily()`
Does a manual `_idempotency_check()` *before* inserting, then inserts with `on_conflict_do_nothing` but never checks whether the insert actually landed a row (unlike `award_points()`, which correctly checks `inserted_id is None`). Two near-simultaneous `/daily` taps can both pass the pre-check and both credit `user.points`, even though only one activity_log row gets written.
**Fix:** After the insert, check `result.rowcount` (or use `.returning()` and check for `None` like `award_points()` does) before mutating `user.points`/`lifetime_points`/`daily_streak`. Bail out with `applied=False, reason="duplicate"` if the insert didn't land.

### 3. Referral can get stuck at `qualified` forever and never pay out
**File:** `bot/engines/referral.py`, `_check_and_reward()`
Only scans rows with `status == "pending"`. If `points_engine.award_points()` fails after the row is flipped to `"qualified"` (transient DB error, etc.), nothing ever re-checks it — the referrer is never paid, silently, forever.
**Fix:** Either (a) do the status flip and the point award in the same transaction so they succeed/fail together, or (b) have `expire_stale_referrals` / a new scheduled job also re-scan `qualified` rows older than N minutes and retry the payout.

### 4. `streak_broken` pet trigger is dead code
**File:** `bot/engines/pet.py` line 101 defines the `streak_broken` branch in `_apply_trigger`, but **nothing in the codebase ever calls it**. `claim_daily()` in `points.py` always fires `PetTriggerEvent(type="points_awarded")` regardless of whether the streak just reset to 1.
**Fix:** In `claim_daily()`, when `new_streak == 1` and the user had a prior non-null `last_daily_at` that's more than a day old (i.e. an actual break, not a first-ever claim), fire `PetTriggerEvent(type="streak_broken")` in addition to (or instead of) `points_awarded`.

### 5. Broken production webhook URL
**File:** `bot/main.py`
```python
webhook_url = f"https://{settings.node_env}.railway.app/webhook"
```
This interpolates `node_env` (literally the string `"production"`) as the subdomain, registering `https://production.railway.app/webhook` with Telegram — not your real Railway domain. **The bot will never receive updates in production with this as-is.**
**Fix:** Add a `railway_public_domain` (or `webhook_base_url`) setting to `config.py`, populate it from Railway's `RAILWAY_PUBLIC_DOMAIN` env var, and use that instead of `node_env`.

### 6. Unhandled Telegram error breaks inline-keyboard navigation
**File:** `bot/adapters/telegram.py`, `handle_callback()`
No `try/except` around any `query.edit_message_text(...)` call. Telegram raises `BadRequest: Message is not modified` whenever the edit content is identical to what's already shown (e.g. user re-taps the same nav button, or taps a button that lands back on unchanged content). This exception is never caught, so the tap silently does nothing — this is very likely the "buttons don't change" issue reported.
**Fix:** Wrap every `edit_message_text` call in a helper that swallows `BadRequest` specifically when the message is `"Message is not modified"`, re-raising anything else. *(I already started this — a `safe_edit()` helper — but stopped when asked not to code without confirmation. Still needs to be finished and wired into all branches of `handle_callback`.)*

### 7. `leaderboard` callback branch doesn't pass `reply_markup`
**File:** `bot/adapters/telegram.py`, `handle_callback()`, `nav_type == "leaderboard"` branch
Every other nav branch explicitly re-attaches `_profile_keyboard(...)`; this one doesn't. Functionally Telegram preserves the prior keyboard when `reply_markup` is omitted, so it's not currently breaking anything, but it's an inconsistency that will bite the next time this code is touched.
**Fix:** Explicitly pass `reply_markup=_profile_keyboard(...)` for consistency (note: this branch doesn't currently receive a `nav_user_id`, so you'd need to thread the acting user's id through, e.g. via `query.from_user.id` → lookup).

### 8. Hardcoded live database password in the repo
**File:** `check_tables.py`
```python
password='@Teenwolf1234'
```
Plaintext Supabase credentials (user, password, host) committed directly in a script. If this was ever pushed to git (especially a public repo), that credential is compromised regardless of what you do to the file going forward.
**Fix (do this first, it's the highest-severity item on this whole list):**
1. Rotate the Supabase database password immediately.
2. Rewrite `check_tables.py` to read `DATABASE_URL` from environment/`.env` like the rest of the app does.
3. Check git history for this file; if it was ever committed/pushed, treat the old password as burned even after rotation.

---

## 🟡 Gaps — written but not wired up, or missing outright

### 9. No `/feed` command
Only the *text* "feed the cat!" exists (in the hungry mood description in `visuals.py`) — there is no command, handler, or energy-boost action behind it. Bot prompts an action it doesn't support.

### 10. No admin command surface at all
`users.is_admin` is defined on the model and never read anywhere in the codebase. There is no `/admin`, `/ban`, `/unban`, or manual point-grant command. The only writer of `admin_actions` is `flag_suspicious_referral()`, which itself is never called (see #12) — so in practice nothing ever writes to that table today.

### 11. Achievements can never unlock — and none exist to unlock anyway
- No code anywhere inserts into `user_achievements`; the "Check Achievement" step from the points-award flow is unimplemented.
- Even if unlock logic existed, the `achievements` table has **zero seed rows** — no migration, fixture, or script inserts a single achievement definition. `/achievements` will show "No achievements exist yet" permanently as-is.
- `streak_milestone` has a defined emoji in `visuals.py` implying a planned achievement/event, but nothing ever triggers it.

### 12. Security functions exist but are never called from live code paths
- `flag_suspicious_referral()` (sybil detection) — defined, unit-tested in isolation, never called from `register_referral()` or anywhere else in the request path.
- `check_ai_rate()` — defined, never called from `handle_message()`; free-chat AI calls currently have **no** rate limit despite this being written.
- `ban_check()` / `leave_check()` on `ReferralEngine` — defined, tested, but **nothing in the Telegram layer calls them**. There's no ban command to trigger `ban_check`, and no `ChatMemberHandler` registered to catch users leaving, so `leave_check` can never fire in production either.

### 13. No join/leave event handling
No `ChatMemberHandler` (or equivalent) is registered anywhere in `create_application()`. The bot has no way of knowing when someone joins or leaves the group via Telegram's native events — this is *why* #12's `leave_check` is unreachable, and also means there's no natural hook for a "welcome" flow triggered by an actual group join (as opposed to `/start` in DM).

### 14. `wallet_address` is a dead field
Column exists on `users`, is unique-constrained, was part of the original Web3 vision — but there is no `/wallet` or `/connectwallet` command anywhere. The field can currently only ever be set by hand in the database.

### 15. Level-up is only announced from `/daily`
The 🎉 level-up message is only shown inside the `daily()` handler (`if result.new_level: ...`). If a user levels up from message-activity points or a referral bonus instead, they receive **no level-up notification** — `award_points()` doesn't return enough info to the caller, and neither `check_message_activity` nor the referral-reward path check for or announce a level change.

### 16. Weekly snapshot does nothing
`points_engine.snapshot_weekly()` is literally:
```python
return {"ok": True, "note": "placeholder — weekly snapshot not yet implemented"}
```
Scheduled every Sunday via cron, but performs no actual snapshot/reset of anything.

### 17. Twitter/X search is a stub
`_twitter_stub()` just logs `"twitter_search: not yet implemented"` every 10 minutes. Confirmed intentional placeholder per the original spec (Ch.9), just flagging it here so it's in one complete list.

### 18. No content-moderation gate before free-chat AI calls
Spec §7.5 calls for staying silent if a message matches a moderation-flagged pattern before sending it to the AI. `handle_message()` has no such check — any mentioned/replied-to message goes straight to the model.

### 19. AI provider is Groq, not Gemini
`bot/ai/brain.py` uses `AsyncGroq` / `mixtral-8x7b-32768`, not Gemini as specified throughout the original spec and brainstorm doc. Not necessarily wrong — just flagging the divergence in case it wasn't an intentional pivot. Also the AI call timeout is `2.0s`, not the `800ms` budget described in spec §7.5, and the "skip the AI call if recent p95 latency is high" performance rule isn't implemented (only hard timeout/error triggers the template fallback).

### 20. No "smart delete" (previous message cleanup)
Confirmed missing — no tracking of the last message Rina sent a given user, so nothing can be auto-deleted when a new command comes in. *(Partial fix already scaffolded — DB columns `last_message_id`/`last_message_chat_id` added to `User`, migration written, `smart_reply()`/`smart_reply_photo()` helpers drafted in `telegram.py` — but not finished or wired into the actual command handlers yet, and nothing has been tested or deployed.)*

---

## 🟢 Cosmetic / naming

### 21. "Egg" doesn't fit a cat
Growth stages (`egg → hatchling → juvenile → adult → elder`) are generic pet-growth terms that don't actually make sense for a cat — cats don't hatch. Suggested rename: `kitten → juvenile → adult → senior → elder` (or similar), pure relabeling — `compute_stage()` only returns string keys, no logic changes needed, just update the literal type, the DB default, and the `visuals.py` mappings together.

### 22. Growth thresholds may be miscalibrated for a small/new community
Current thresholds (1,000 / 10,000 / 50,000 / 200,000 **total lifetime points summed across every user ever**) are what's currently making Rina "stuck on egg" for smaller/newer communities — this is working as coded, but worth deciding if the numbers should scale down.

---

## Suggested priority order

1. **Rotate the exposed DB password** (#8) — do this before anything else, independent of code changes.
2. **Bug fixes that corrupt game state** (#1, #2, #3) — these silently produce wrong points/referrals right now.
3. **Production blocker** (#5) — webhook URL bug will stop the bot working at all once deployed.
4. **UX-visible breakage** (#6, #7) — the button issue you're actually experiency day-to-day.
5. Everything else in 🟡/🟢 — feature completion, prioritize based on what you actually want live first (my suggestion was `/feed` + achievement unlocking + seed data + wiring `leave_check`/`ban_check`, since those make existing schema do something real).
