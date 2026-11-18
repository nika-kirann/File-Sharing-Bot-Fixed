# File Sharing Bot
# Modified 2026-11-18 from CodeXBotz/File-Sharing-Bot (GPL-3.0).
# A join request is remembered so "Try again" works before a human approves it.

import logging

from pyrogram.types import ChatJoinRequest

from bot import Bot
from config import FORCE_SUB_CHANNEL, JOIN_REQUEST_ENABLE
from database.database import add_join_request

log = logging.getLogger(__name__)


@Bot.on_chat_join_request()
async def remember_join_request(client: Bot, request: ChatJoinRequest):
    if not JOIN_REQUEST_ENABLE or not FORCE_SUB_CHANNEL:
        return
    chat_id = request.chat.id if request.chat else None
    expected = getattr(client, "force_sub_id", 0) or None
    if isinstance(expected, int) and chat_id != expected:
        return
    if expected is None and isinstance(FORCE_SUB_CHANNEL, int) and chat_id != FORCE_SUB_CHANNEL:
        return
    user = request.from_user
    if user is None:
        return
    try:
        await add_join_request(user.id)
    except Exception:
        log.exception("Could not store a join request for %s", user.id)
