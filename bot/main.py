from contextlib import asynccontextmanager

from telegram import Update
from telegram.ext import Application
from fastapi import FastAPI, Request

from bot.config import settings
from bot.adapters.telegram import create_application
from bot.scheduler import schedule, setup_scheduler
from bot.security import verify_webhook_secret, check_command_rate, logger


tg_app: Application | None = None


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global tg_app
    if settings.telegram_bot_token:
        tg_app = create_application()
        await tg_app.initialize()
        if settings.node_env == "production":
            webhook_url = f"{settings.webhook_base_url}/webhook" if settings.webhook_base_url else ""
            await tg_app.bot.set_webhook(webhook_url, secret_token=settings.telegram_webhook_secret)
        else:
            await tg_app.start()
            if tg_app.updater:
                await tg_app.updater.start_polling()
    setup_scheduler()
    schedule.start()
    logger.info(f"Rina bot running on port {settings.port}")
    yield
    schedule.stop()
    if tg_app:
        await tg_app.stop()
        await tg_app.shutdown()


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/webhook")
async def webhook(request: Request):
    secret = request.headers.get("x-telegram-bot-api-secret-token")
    if not verify_webhook_secret(secret):
        return {"ok": False, "error": "unauthorized"}

    if tg_app is None:
        return {"ok": False, "error": "bot not configured"}

    body = await request.json()
    update = Update.de_json(body, tg_app.bot)

    user_id = None
    if update.effective_user:
        user_id = update.effective_user.id
        if not check_command_rate(user_id):
            return {"ok": False, "error": "rate_limited"}

    await tg_app.process_update(update)
    return {"ok": True}
