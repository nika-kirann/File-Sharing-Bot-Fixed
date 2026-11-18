# File Sharing Bot
# Modified 2026-11-18 from CodeXBotz/File-Sharing-Bot (GPL-3.0).

from __future__ import annotations

import asyncio
import logging

from pyrogram import filters
from pyrogram.enums import ParseMode
from pyrogram.errors import FloodWait
from pyrogram.errors.exceptions.bad_request_400 import (
    InputUserDeactivated,
    PeerIdInvalid,
    UserIdInvalid,
)
from pyrogram.errors.exceptions.bad_request_400 import (
    UserIsBlocked as UserIsBlockedBadRequest,
)
from pyrogram.errors.exceptions.forbidden_403 import UserDeleted
from pyrogram.errors.exceptions.forbidden_403 import (
    UserIsBlocked as UserIsBlockedForbidden,
)
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import Bot
from config import (
    ADMINS,
    AUTO_DELETE_MSG,
    AUTO_DELETE_TIME,
    CUSTOM_CAPTION,
    DISABLE_CHANNEL_BUTTON,
    FORCE_MSG,
    PROTECT_CONTENT,
    START_MSG,
    START_PIC,
)
from database.database import (
    add_user,
    del_user,
    iter_user_ids,
    present_user,
    queue_deletion,
    user_count,
)
from helper_func import (
    PayloadError,
    decode_payload,
    fill_user,
    flood_seconds,
    get_messages,
    subscribed,
)

log = logging.getLogger(__name__)

_DROP_USER = (
    UserIsBlockedBadRequest,
    UserIsBlockedForbidden,
    InputUserDeactivated,
    UserDeleted,
    PeerIdInvalid,
    UserIdInvalid,
)


def _caption_for(msg) -> str | None:
    if not (CUSTOM_CAPTION and msg.document):
        return None
    filename = msg.document.file_name or ""
    previous = msg.caption.html if msg.caption else ""
    try:
        return CUSTOM_CAPTION.format(previouscaption=previous, filename=filename)
    except Exception:
        log.warning("CUSTOM_CAPTION could not be formatted; using the original caption")
        return None


async def _copy_message(msg, user_id: int):
    kwargs = {
        "chat_id": user_id,
        "protect_content": PROTECT_CONTENT,
    }
    caption = _caption_for(msg)
    if caption is not None:
        kwargs["caption"] = caption
        kwargs["parse_mode"] = ParseMode.HTML
    # Omitting reply_markup keeps the original buttons. Passing None strips the
    # share button this bot attaches to database-channel posts.
    if not DISABLE_CHANNEL_BUTTON:
        kwargs["reply_markup"] = None
    try:
        return await msg.copy(**kwargs)
    except FloodWait as exc:
        await asyncio.sleep(flood_seconds(exc))
        return await msg.copy(**kwargs)


async def _send_welcome(message: Message) -> None:
    user = message.from_user
    buttons = InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("About", callback_data="about"),
            InlineKeyboardButton("Close", callback_data="close"),
        ]]
    )
    caption = fill_user(START_MSG, user)
    if START_PIC:
        try:
            await message.reply_photo(
                photo=START_PIC,
                caption=caption,
                reply_markup=buttons,
                quote=True,
            )
            return
        except Exception:
            log.warning("START_PIC could not be sent; falling back to text")
    await message.reply_text(
        caption,
        reply_markup=buttons,
        disable_web_page_preview=True,
        quote=True,
    )


@Bot.on_message(filters.command("start") & filters.private & subscribed)
async def start_command(client: Bot, message: Message):
    user_id = message.from_user.id
    try:
        if not await present_user(user_id):
            await add_user(user_id)
    except Exception:
        log.exception("Could not store user %s", user_id)

    command = message.command or []
    if len(command) < 2:
        await _send_welcome(message)
        return

    try:
        ids = decode_payload(command[1], client.db_channel.id)
    except PayloadError as exc:
        await message.reply_text(str(exc), quote=True)
        return

    temp = await message.reply("Please wait...")
    try:
        messages = await get_messages(client, ids)
    except Exception:
        log.exception("Fetching linked messages failed")
        await message.reply_text("Something went wrong.")
        return
    finally:
        try:
            await temp.delete()
        except Exception:
            pass

    delivered = []
    for msg in messages:
        if msg is None or getattr(msg, "empty", False):
            continue
        try:
            copied = await _copy_message(msg, user_id)
        except Exception:
            log.exception("Could not copy message %s", getattr(msg, "id", "?"))
            continue
        if copied:
            delivered.append(copied)
        await asyncio.sleep(0.4)

    if not delivered:
        await message.reply_text(
            "That file is missing or could not be sent.",
            quote=True,
        )
        return

    if AUTO_DELETE_TIME > 0:
        try:
            notice_text = AUTO_DELETE_MSG.format(time=AUTO_DELETE_TIME)
        except Exception:
            notice_text = AUTO_DELETE_MSG.replace("{time}", str(AUTO_DELETE_TIME))
        notice = await client.send_message(user_id, notice_text)
        try:
            await queue_deletion(
                user_id,
                [item.id for item in delivered],
                notice.chat.id,
                notice.id,
            )
        except Exception:
            log.exception("Could not schedule auto-delete")


@Bot.on_message(filters.command("start") & filters.private)
async def not_joined(client: Bot, message: Message):
    if not client.invitelink:
        await message.reply_text(
            "Force-subscribe is enabled, but the invite link is not ready. "
            "Ask the bot owner to check the logs.",
            quote=True,
        )
        return

    buttons = [[InlineKeyboardButton("Join Channel", url=client.invitelink)]]
    command = message.command or []
    if len(command) > 1:
        buttons.append(
            [
                InlineKeyboardButton(
                    "Try Again",
                    url=f"https://t.me/{client.username}?start={command[1]}",
                )
            ]
        )
    await message.reply(
        fill_user(FORCE_MSG, message.from_user),
        reply_markup=InlineKeyboardMarkup(buttons),
        quote=True,
        disable_web_page_preview=True,
    )


@Bot.on_message(filters.command("users") & filters.private & filters.user(ADMINS))
async def get_users(client: Bot, message: Message):
    msg = await message.reply("<b>Processing...</b>")
    count = await user_count()
    await msg.edit(f"{count} users are using this bot")


@Bot.on_message(filters.private & filters.command("broadcast") & filters.user(ADMINS))
async def broadcast(client: Bot, message: Message):
    if not message.reply_to_message:
        msg = await message.reply(
            "<code>Reply to the message you want to broadcast.</code>"
        )
        await asyncio.sleep(8)
        await msg.delete()
        return

    query = message.reply_to_message
    total = successful = blocked = unsuccessful = 0
    status = await message.reply("<i>Broadcasting. This can take a while.</i>")

    async for chat_id in iter_user_ids():
        total += 1
        try:
            await query.copy(chat_id)
            successful += 1
        except FloodWait as exc:
            await asyncio.sleep(flood_seconds(exc))
            try:
                await query.copy(chat_id)
                successful += 1
            except _DROP_USER:
                await del_user(chat_id)
                blocked += 1
            except Exception:
                unsuccessful += 1
        except _DROP_USER:
            await del_user(chat_id)
            blocked += 1
        except Exception:
            unsuccessful += 1

    await status.edit(
        "<b><u>Broadcast finished</u></b>\n\n"
        f"Total users: <code>{total}</code>\n"
        f"Successful: <code>{successful}</code>\n"
        f"Removed (blocked or gone): <code>{blocked}</code>\n"
        f"Unsuccessful: <code>{unsuccessful}</code>"
    )
