# File Sharing Bot
# Modified 2026-11-18 from CodeXBotz/File-Sharing-Bot (GPL-3.0).

import logging

from pyrogram import filters
from pyrogram.errors import ListenerTimeout
from pyrogram.types import Message

from bot import Bot
from config import ADMINS
from helper_func import (
    PayloadError,
    encode_payload,
    get_message_id,
    link_keyboard,
    public_link,
)

log = logging.getLogger(__name__)

_ASK_FILTERS = filters.forwarded | (filters.text & ~filters.forwarded)
_PROMPT_FIRST = (
    "Forward the first message from the database channel "
    "(forward it as a copy, with the quote), or send the post link."
)
_PROMPT_LAST = (
    "Forward the last message from the database channel, or send the post link."
)
_PROMPT_ONE = (
    "Forward a message from the database channel, or send the post link."
)
_BAD = (
    "That message is not from the database channel. "
    "Forward the channel post, or send its t.me link."
)


async def _ask_for_id(client: Bot, message: Message, prompt: str) -> int | None:
    while True:
        try:
            reply = await client.ask(
                chat_id=message.from_user.id,
                text=prompt,
                filters=_ASK_FILTERS,
                timeout=60,
                user_id=message.from_user.id,
            )
        except (ListenerTimeout, TimeoutError):
            await message.reply("Timed out. Send the command again when you are ready.")
            return None
        except Exception:
            log.exception("Waiting for a database-channel message failed")
            await message.reply("Could not read the next message. Send the command again.")
            return None
        msg_id = get_message_id(client, reply)
        if msg_id:
            return msg_id
        await reply.reply(_BAD, quote=True)


async def _send_link(client: Bot, target: Message, message_ids: list[int]) -> None:
    try:
        token = encode_payload(message_ids, client.db_channel.id)
    except PayloadError as exc:
        await target.reply_text(str(exc), quote=True)
        return
    link = public_link(client.username, token)
    await target.reply_text(
        f"<b>Here is your link</b>\n\n{link}",
        quote=True,
        reply_markup=link_keyboard(link),
    )


@Bot.on_message(filters.private & filters.user(ADMINS) & filters.command("batch"))
async def batch(client: Bot, message: Message):
    first = await _ask_for_id(client, message, _PROMPT_FIRST)
    if not first:
        return
    second = await _ask_for_id(client, message, _PROMPT_LAST)
    if not second:
        return
    await _send_link(client, message, [first, second])


@Bot.on_message(filters.private & filters.user(ADMINS) & filters.command("genlink"))
async def link_generator(client: Bot, message: Message):
    msg_id = await _ask_for_id(client, message, _PROMPT_ONE)
    if not msg_id:
        return
    await _send_link(client, message, [msg_id])
