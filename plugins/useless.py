# File Sharing Bot
# Modified 2026-11-18 from CodeXBotz/File-Sharing-Bot (GPL-3.0).

from datetime import datetime, timezone

from pyrogram import filters
from pyrogram.types import Message

from bot import Bot
from config import ADMINS, BOT_STATS_TEXT, KNOWN_COMMANDS, USER_REPLY_TEXT
from helper_func import get_readable_time


def _fallback_filter(_flt, _client, message: Message) -> bool:
    user = message.from_user
    if user is not None and user.id in ADMINS:
        return False
    text = message.text or ""
    if text.startswith("/"):
        command = text.split(maxsplit=1)[0][1:].split("@", 1)[0].lower()
        if command in KNOWN_COMMANDS:
            return False
    return True


@Bot.on_message(filters.command("stats") & filters.user(ADMINS))
async def stats(bot: Bot, message: Message):
    started = getattr(bot, "start_time", None) or datetime.now(timezone.utc)
    uptime = get_readable_time(int((datetime.now(timezone.utc) - started).total_seconds()))
    try:
        text = BOT_STATS_TEXT.format(uptime=uptime)
    except Exception:
        text = uptime
    await message.reply(text)


@Bot.on_message(filters.private & filters.incoming & filters.create(_fallback_filter))
async def fallback(_bot: Bot, message: Message):
    if USER_REPLY_TEXT:
        await message.reply(USER_REPLY_TEXT)
