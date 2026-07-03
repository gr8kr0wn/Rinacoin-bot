"""Debug polling issue."""
import asyncio
import logging
from telegram.ext import Application

logging.basicConfig(level=logging.DEBUG)

TOKEN = "8729486088:AAElJbqBVx0IqH_UEc0kKYv6nAfk2xsBXJY"

async def test():
    app = Application.builder().token(TOKEN).build()
    await app.initialize()
    await app.start()
    print(f"Updater: {app.updater}")
    if app.updater:
        print(f"Updater running: {app.updater.running}")
    await asyncio.sleep(3)
    updates = await app.bot.get_updates(timeout=1)
    print(f"Pending updates: {len(updates)}")
    await app.stop()
    await app.shutdown()

asyncio.run(test())
