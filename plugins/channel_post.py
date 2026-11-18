# File Sharing Bot
# Modified 2026-11-18 from CodeXBotz/File-Sharing-Bot (GPL-3.0).

import asyncio
import logging

from pyrogram import filters
from pyrogram.errors import FloodWait
from pyrogram.types import Message

from bot import Bot
from config import ADMINS, CHANNEL_ID, DISABLE_CHANNEL_BUTTON, KNOWN_COMMANDS
from helper_func import (
    PayloadError,
    encode_payload,
    flood_seconds,
    link_keyboard,
    public_link,
)

log = logging.getLogger(__name__)


def _ready(client: Bot) -> bool:
    return getattr(client, "db_channel", None) is not None and bool(client.username)


async def _copy_into_channel(client: Bot, message: Message):
    try:
        return await message.copy(
            chat_id=client.db_channel.id,
            disable_notification=True,
        )
    except FloodWait as exc:
        await asyncio.sleep(flood_seconds(exc))
        return await message.copy(
            chat_id=client.db_channel.id,
            disable_notification=True,
        )


async def _attach_share_button(message, markup) -> None:
    try:
        await message.edit_reply_markup(markup)
    except FloodWait as exc:
        await asyncio.sleep(flood_seconds(exc))
        await message.edit_reply_markup(markup)


@Bot.on_message(
    filters.private
    & filters.user(ADMINS)
    & ~filters.command(list(KNOWN_COMMANDS))
)
async def channel_post(client: Bot, message: Message):
    reply = await message.reply_text("Please wait...", quote=True)
    if not _ready(client):
        await reply.edit_text("The bot is still starting. Try again in a moment.")
        return
    try:
        posted = await _copy_into_channel(client, message)
    except Exception:
        log.exception("Could not copy a message into the database channel")
        await reply.edit_text("Something went wrong.")
        return

    try:
        token = encode_payload([posted.id], client.db_channel.id)
    except PayloadError as exc:
        await reply.edit_text(str(exc))
        return
    link = public_link(client.username, token)
    markup = link_keyboard(link)
    await reply.edit(
        f"<b>Here is your link</b>\n\n{link}",
        reply_markup=markup,
        disable_web_page_preview=True,
    )
    if DISABLE_CHANNEL_BUTTON:
        return
    try:
        await _attach_share_button(posted, markup)
    except Exception:
        log.info("Could not attach the share button to %s", posted.id)


@Bot.on_message(filters.channel & filters.incoming & filters.chat(CHANNEL_ID))
async def new_post(client: Bot, message: Message):
    if DISABLE_CHANNEL_BUTTON or not _ready(client):
        return
    try:
        token = encode_payload([message.id], client.db_channel.id)
        await _attach_share_button(message, link_keyboard(public_link(client.username, token)))
    except PayloadError as exc:
        log.info("Skipped channel message %s: %s", message.id, exc)
    except Exception:
        log.info("Could not attach the share button to channel message %s", message.id)
