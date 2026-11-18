# File Sharing Bot
# Modified 2026-11-18 from CodeXBotz/File-Sharing-Bot (GPL-3.0).
# Payload ids are multiplied by the channel id and recovered with integer division.

from __future__ import annotations

import asyncio
import base64
import binascii
import logging
import re
from html import escape
from urllib.parse import quote

from pyrogram import filters
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import FloodWait, UserNotParticipant
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import (
    ADMINS,
    AUTO_DEL_SUCCESS_MSG,
    FORCE_SUB_CHANNEL,
    JOIN_REQUEST_ENABLE,
    MAX_BATCH_MESSAGES,
    START_PAYLOAD_LIMIT,
)
from database.database import (
    drop_deletion,
    due_deletions,
    has_join_request,
    reschedule_deletion,
)

LOGGER = logging.getLogger(__name__)

_MEMBER_OK = {
    ChatMemberStatus.OWNER,
    ChatMemberStatus.ADMINISTRATOR,
    ChatMemberStatus.MEMBER,
    ChatMemberStatus.RESTRICTED,
}
_LINK_RE = re.compile(
    r"(?:https?://)?(?:www\.)?(?:t\.me|telegram\.me|telegram\.dog)/(?:c/)?"
    r"([A-Za-z0-9_]+)/(\d+)",
    re.IGNORECASE,
)


class PayloadError(ValueError):
    """A file link could not be encoded or decoded."""


def flood_seconds(exc: BaseException) -> int:
    """Seconds to wait after a FloodWait, on Pyrogram 2 and Pyrofork."""
    raw = getattr(exc, "value", None)
    if raw is None:
        raw = getattr(exc, "x", 1)
    try:
        seconds = int(raw)
    except (TypeError, ValueError):
        seconds = 1
    return max(seconds, 1)


def encode(text: str) -> str:
    encoded = base64.urlsafe_b64encode(text.encode("ascii")).decode("ascii")
    return encoded.rstrip("=")


def decode(token: str) -> str:
    padded = token.strip().strip("=")
    padded += "=" * (-len(padded) % 4)
    try:
        return base64.urlsafe_b64decode(padded.encode("ascii")).decode("ascii")
    except (binascii.Error, UnicodeError) as exc:
        raise PayloadError("link payload is not valid") from exc


def encode_payload(message_ids: list[int], channel_id: int) -> str:
    """Build a Telegram ``/start`` payload for one file or a batch range."""
    if len(message_ids) not in (1, 2):
        raise PayloadError("a link can contain one id or a start and end id")
    divisor = abs(int(channel_id))
    if divisor == 0:
        raise PayloadError("channel id is not configured")
    parts = ["get", *(str(int(msg_id) * divisor) for msg_id in message_ids)]
    token = encode("-".join(parts))
    if len(token) > START_PAYLOAD_LIMIT:
        raise PayloadError(
            "generated link is longer than Telegram's 64-character start limit; "
            "choose a smaller batch"
        )
    return token


def decode_payload(token: str, channel_id: int) -> list[int]:
    """Reverse :func:`encode_payload` without floating-point rounding."""
    decoded = decode(token.strip())
    parts = decoded.split("-")
    if len(parts) < 2 or parts[0] != "get":
        raise PayloadError("this link is not a file link")
    divisor = abs(int(channel_id))
    if divisor == 0:
        raise PayloadError("channel id is not configured")

    endpoints: list[int] = []
    for piece in parts[1:]:
        if not piece.isdigit():
            raise PayloadError("this link is not a file link")
        value = int(piece)
        if value % divisor != 0:
            raise PayloadError("this link does not belong to the database channel")
        endpoints.append(value // divisor)

    if len(endpoints) == 1:
        return endpoints
    if len(endpoints) != 2:
        raise PayloadError("this link is not a file link")

    start, end = endpoints
    if start <= end:
        count = end - start + 1
        ids = list(range(start, end + 1))
    else:
        count = start - end + 1
        ids = list(range(start, end - 1, -1))
    if count > MAX_BATCH_MESSAGES:
        raise PayloadError(
            f"this batch has {count} files; the limit is {MAX_BATCH_MESSAGES}"
        )
    return ids


def public_link(username: str, token: str) -> str:
    return f"https://t.me/{username}?start={token}"


def telegram_share_url(link: str) -> str:
    """Share URL with the deep link encoded as a single query value.

    A raw ``?start=`` inside the ``url`` parameter is parsed as a second
    query argument, so the shared link loses its payload.
    """
    return "https://t.me/share/url?url=" + quote(link, safe="")


def link_keyboard(link: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("Share URL", url=telegram_share_url(link))]]
    )


def fill_user(template: str, user) -> str:
    """Fill a message template. User text is escaped; ``mention`` stays HTML."""
    values = {
        "first": escape(getattr(user, "first_name", None) or ""),
        "last": escape(getattr(user, "last_name", None) or ""),
        "username": (
            "@" + escape(user.username) if getattr(user, "username", None) else ""
        ),
        "mention": getattr(user, "mention", None)
        or escape(getattr(user, "first_name", None) or "user"),
        "id": getattr(user, "id", ""),
    }
    try:
        return template.format(**values)
    except Exception:
        LOGGER.warning("Message template has an unknown placeholder")
        return template


def get_readable_time(seconds: int) -> str:
    remaining = max(int(seconds), 0)
    parts: list[str] = []
    for divisor, suffix in ((60, "s"), (60, "m"), (24, "h"), (24, "days")):
        remaining, result = divmod(remaining, divisor)
        parts.append(f"{int(result)}{suffix}")
        if remaining == 0:
            break
    if not parts:
        return "0s"
    if len(parts) == 4:
        days = parts.pop()
        parts.reverse()
        return f"{days}, " + ":".join(parts)
    parts.reverse()
    return ":".join(parts)


def get_message_id(client, message) -> int:
    """Return the database-channel message id, or 0 when it cannot be resolved."""
    origin = getattr(message, "forward_origin", None)
    if origin is not None:
        chat = getattr(origin, "chat", None) or getattr(origin, "sender_chat", None)
        origin_id = getattr(origin, "message_id", None)
        if chat is not None and origin_id and chat.id == client.db_channel.id:
            return int(origin_id)
        return 0

    # Objects that predate forward_origin (and unit-test doubles).
    if not hasattr(message, "forward_origin"):
        forwarded_chat = getattr(message, "forward_from_chat", None)
        if forwarded_chat is not None:
            if forwarded_chat.id == client.db_channel.id:
                return int(getattr(message, "forward_from_message_id", 0) or 0)
            return 0
        if getattr(message, "forward_sender_name", None):
            return 0

    text = getattr(message, "text", None) or ""
    match = _LINK_RE.search(text.strip())
    if not match:
        return 0
    channel_part, msg_id_text = match.group(1), match.group(2)
    msg_id = int(msg_id_text)
    if channel_part.isdigit():
        if f"-100{channel_part}" == str(client.db_channel.id):
            return msg_id
        return 0
    username = getattr(client.db_channel, "username", None) or ""
    if channel_part.lower() == username.lower():
        return msg_id
    return 0


async def get_messages(client, message_ids):
    messages = []
    ids = [int(mid) for mid in message_ids]
    total = 0
    while total < len(ids):
        chunk = ids[total : total + 200]
        try:
            fetched = await client.get_messages(
                chat_id=client.db_channel.id,
                message_ids=chunk,
                replies=0,
            )
        except FloodWait as exc:
            await asyncio.sleep(flood_seconds(exc))
            fetched = await client.get_messages(
                chat_id=client.db_channel.id,
                message_ids=chunk,
                replies=0,
            )
        except Exception:
            LOGGER.exception("Failed to fetch message ids %s", chunk)
            total += len(chunk)
            continue
        if fetched is None:
            fetched = []
        elif not isinstance(fetched, list):
            fetched = [fetched]
        messages.extend(fetched)
        total += len(chunk)
    return messages


async def delete_message_ids(client, chat_id: int, message_ids: list[int]) -> None:
    ids = [int(mid) for mid in message_ids if mid]
    for offset in range(0, len(ids), 100):
        chunk = ids[offset : offset + 100]
        try:
            await client.delete_messages(chat_id=chat_id, message_ids=chunk)
        except FloodWait as exc:
            await asyncio.sleep(flood_seconds(exc))
            await client.delete_messages(chat_id=chat_id, message_ids=chunk)


async def deletion_worker(client) -> None:
    """Delete files whose deadline has passed, including after a restart."""
    while True:
        try:
            jobs = await due_deletions()
            for job in jobs:
                attempts = int(job.get("attempts", 0)) + 1
                try:
                    await delete_message_ids(
                        client, job["chat_id"], job.get("message_ids") or []
                    )
                    try:
                        await client.edit_message_text(
                            job["notice_chat_id"],
                            job["notice_id"],
                            AUTO_DEL_SUCCESS_MSG,
                        )
                    except Exception:
                        LOGGER.info(
                            "Could not edit the auto-delete notice in %s",
                            job.get("notice_chat_id"),
                        )
                    await drop_deletion(job["_id"])
                except FloodWait as exc:
                    delay = flood_seconds(exc)
                    if attempts >= 5:
                        await drop_deletion(job["_id"])
                    else:
                        await reschedule_deletion(
                            job["_id"], attempts=attempts, delay=delay
                        )
                except Exception:
                    LOGGER.exception("Auto-delete failed for job %s", job.get("_id"))
                    if attempts >= 5:
                        await drop_deletion(job["_id"])
                    else:
                        await reschedule_deletion(
                            job["_id"], attempts=attempts, delay=30
                        )
        except asyncio.CancelledError:
            raise
        except Exception:
            LOGGER.exception("Auto-delete pass failed")
        await asyncio.sleep(5)


def _member_is_joined(status) -> bool:
    if status in _MEMBER_OK:
        return True
    name = getattr(status, "name", str(status)).split(".")[-1].upper()
    return name in {"OWNER", "ADMINISTRATOR", "MEMBER", "RESTRICTED"}


async def is_subscribed(_filter, client, update) -> bool:
    if not FORCE_SUB_CHANNEL:
        return True
    user = getattr(update, "from_user", None)
    if user is None:
        return False
    if user.id in ADMINS:
        return True
    try:
        member = await client.get_chat_member(FORCE_SUB_CHANNEL, user.id)
    except UserNotParticipant:
        member = None
    except FloodWait as exc:
        await asyncio.sleep(flood_seconds(exc))
        try:
            member = await client.get_chat_member(FORCE_SUB_CHANNEL, user.id)
        except UserNotParticipant:
            member = None
        except Exception:
            LOGGER.exception("Force-sub membership check failed")
            return False
    except Exception:
        LOGGER.exception("Force-sub membership check failed")
        return False
    if member is not None and _member_is_joined(member.status):
        return True
    if JOIN_REQUEST_ENABLE:
        try:
            return await has_join_request(user.id)
        except Exception:
            LOGGER.exception("Join-request lookup failed")
    return False


subscribed = filters.create(is_subscribed)
